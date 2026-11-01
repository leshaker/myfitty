"""DuckDB access: short-lived connections, schema, and threshold history.

DuckDB allows one read-write process at a time and Streamlit reruns the script on every
interaction, so nothing here holds a connection open between calls.
"""
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import duckdb

from myfitty.config import load_config

METRICS = ("ftp", "threshold_hr", "max_hr")

SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS activity_id_seq;
CREATE TABLE IF NOT EXISTS activities (
    id BIGINT PRIMARY KEY DEFAULT nextval('activity_id_seq'),
    start_time TIMESTAMP NOT NULL,          -- UTC
    local_date DATE NOT NULL,               -- start date in the machine's local timezone
    device_serial VARCHAR NOT NULL,         -- serial number, or 'sha256:<file hash>' when absent
    sport VARCHAR NOT NULL,
    sub_sport VARCHAR,
    source_path VARCHAR,
    sample_path VARCHAR,                    -- Parquet file, relative to the samples dir
    elapsed_seconds DOUBLE,
    moving_seconds DOUBLE,
    distance_m DOUBLE,
    avg_hr DOUBLE,
    max_hr DOUBLE,
    avg_power DOUBLE,
    normalized_power DOUBLE,
    hr_histogram VARCHAR,                   -- JSON {bpm: seconds}
    tss DOUBLE,
    tss_method VARCHAR,                     -- 'power' | 'hr'
    trimp DOUBLE,
    ftp_used DOUBLE,
    thr_hr_used DOUBLE,
    max_hr_used DOUBLE,
    unscored_reason VARCHAR,                -- 'no_data' | 'no_threshold'
    imported_at TIMESTAMP DEFAULT current_timestamp,
    UNIQUE (start_time, device_serial)
);
CREATE TABLE IF NOT EXISTS threshold_entries (
    metric VARCHAR NOT NULL,
    effective_from DATE NOT NULL,
    value DOUBLE NOT NULL,
    PRIMARY KEY (metric, effective_from)
);
CREATE TABLE IF NOT EXISTS ingest_failures (
    path VARCHAR PRIMARY KEY,
    reason VARCHAR NOT NULL,
    failed_at TIMESTAMP DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS source_files (
    path VARCHAR PRIMARY KEY,
    size BIGINT NOT NULL,
    mtime DOUBLE NOT NULL,
    status VARCHAR NOT NULL                 -- 'imported' | 'duplicate' | 'failed' | 'skipped'
);
"""


@contextmanager
def connect(path: Path | None = None, retries: int = 50, delay: float = 0.1):
    """Open the database, apply the schema, and close it on exit.

    Retries briefly when another process (e.g. a CLI import) holds the file lock.
    """
    path = Path(path) if path is not None else load_config().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            con = duckdb.connect(str(path))
            break
        except duckdb.IOException:
            if attempt == retries - 1:
                raise
            time.sleep(delay)
    try:
        con.execute(SCHEMA)
        yield con
    finally:
        con.close()


# --- thresholds -------------------------------------------------------------

def _check_metric(metric: str) -> None:
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; expected one of {METRICS}")


def list_thresholds(con, metric: str | None = None) -> list[tuple[str, date, float]]:
    q = "SELECT metric, effective_from, value FROM threshold_entries"
    args = []
    if metric:
        _check_metric(metric)
        q += " WHERE metric = ?"
        args.append(metric)
    return con.execute(q + " ORDER BY metric, effective_from", args).fetchall()


def threshold_on(con, metric: str, on: date) -> float | None:
    """Latest entry effective on or before `on`; else the earliest entry; else None."""
    _check_metric(metric)
    row = con.execute(
        "SELECT value FROM threshold_entries WHERE metric = ? AND effective_from <= ? "
        "ORDER BY effective_from DESC LIMIT 1", [metric, on]).fetchone()
    if row is None:
        row = con.execute(
            "SELECT value FROM threshold_entries WHERE metric = ? "
            "ORDER BY effective_from LIMIT 1", [metric]).fetchone()
    return row[0] if row else None


def thresholds_on(con, on: date) -> dict[str, float | None]:
    return {m: threshold_on(con, m, on) for m in METRICS}


def _affected_range(con, metric: str, d: date, *, earliest_before: bool, earliest_after: bool):
    """Dates whose applicable `metric` entry may change: [start, end), None meaning unbounded."""
    nxt = con.execute(
        "SELECT min(effective_from) FROM threshold_entries WHERE metric = ? AND effective_from > ?",
        [metric, d]).fetchone()[0]
    start = None if (earliest_before or earliest_after) else d
    return start, nxt


def _is_earliest(con, metric: str, d: date) -> bool:
    return con.execute(
        "SELECT count(*) = 0 FROM threshold_entries WHERE metric = ? AND effective_from < ?",
        [metric, d]).fetchone()[0]


def _validate(con, metric: str, d: date, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise ValueError(f"{metric} must be a positive number, got {value!r}")
    if metric == "threshold_hr":
        mx = threshold_on(con, "max_hr", d)
        if mx is not None and value > mx:
            raise ValueError(f"threshold_hr {value} exceeds max_hr {mx} effective on {d}")
    elif metric == "max_hr":
        th = threshold_on(con, "threshold_hr", d)
        if th is not None and th > value:
            raise ValueError(f"max_hr {value} is below threshold_hr {th} effective on {d}")


def set_threshold(con, metric: str, effective_from: date, value: float):
    """Add or replace the entry for (metric, date).

    Returns the (start, end) date range whose scores may change (None = unbounded), for rescoring.
    """
    _check_metric(metric)
    _validate(con, metric, effective_from, value)
    before = _is_earliest(con, metric, effective_from)
    con.execute("INSERT OR REPLACE INTO threshold_entries VALUES (?, ?, ?)",
                [metric, effective_from, float(value)])
    return _affected_range(con, metric, effective_from,
                           earliest_before=before, earliest_after=before)


def delete_threshold(con, metric: str, effective_from: date):
    """Delete an entry; returns the affected range, or None if no such entry existed."""
    _check_metric(metric)
    exists = con.execute(
        "SELECT count(*) FROM threshold_entries WHERE metric = ? AND effective_from = ?",
        [metric, effective_from]).fetchone()[0]
    if not exists:
        return None
    earliest = _is_earliest(con, metric, effective_from)
    con.execute("DELETE FROM threshold_entries WHERE metric = ? AND effective_from = ?",
                [metric, effective_from])
    return _affected_range(con, metric, effective_from,
                           earliest_before=earliest, earliest_after=earliest)
