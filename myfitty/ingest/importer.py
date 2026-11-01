"""Scan a folder of FIT files and import new activities."""
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path

import duckdb
import pandas as pd

from myfitty import db
from myfitty.config import Config, load_config
from myfitty.ingest.parser import NotAnActivity, parse_fit
from myfitty.ingest.samples import sample_relpath, write_samples
from myfitty.ingest.tracks import route_row
from myfitty.metrics.scoring import score_activity

MIN_AGE_SECONDS = 2.0  # newer files may still be being written


@dataclass
class ScanResult:
    imported: int = 0
    duplicates: int = 0
    unchanged: int = 0
    deferred: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (filename, reason)
    folder_missing: bool = False

    def summary(self) -> str:
        parts = [f"{self.imported} imported", f"{self.duplicates} duplicate",
                 f"{self.unchanged} unchanged", f"{len(self.failures)} failed"]
        if self.deferred:
            parts.append(f"{self.deferred} deferred")
        return ", ".join(parts)


def scan(con, cfg: Config | None = None, now: float | None = None, retry_failed: bool = False) -> ScanResult:
    """Import every new or changed `.fit` file under the configured folder (which is only read).

    Scans run one at a time within the process: a second session that opens while one is running
    waits, then finds the files already imported. Unchanged files that failed earlier are skipped too,
    unless `retry_failed` is set (e.g. after fixing the parser).
    """
    with db.WRITE_LOCK:
        return _scan(con, cfg or load_config(), now, retry_failed)


def _backfill_max_power(con, samples_dir) -> None:
    """Fill max_power for activities imported before the column existed, from their samples."""
    rows = con.execute("SELECT id, sample_path FROM activities WHERE max_power IS NULL "
                       "AND avg_power IS NOT NULL AND sample_path IS NOT NULL").fetchall()
    for aid, rel in rows:
        try:
            mx = pd.read_parquet(samples_dir / rel, columns=["power"])["power"].max()
        except (OSError, ValueError, KeyError):
            continue  # samples missing: leave it null rather than fail the scan
        if pd.notna(mx):
            con.execute("UPDATE activities SET max_power = ? WHERE id = ?", [float(mx), aid])


def _read_positions(samples_dir, rel):
    """(t, lat, lon) columns of an activity's samples file."""
    df = pd.read_parquet(samples_dir / rel, columns=["t", "lat", "lon"])
    return df["t"], df["lat"], df["lon"]


def _backfill_routes(con, samples_dir) -> None:
    """Create routes for activities that have samples but no route row, from the samples alone."""
    rows = con.execute("SELECT a.id, a.sub_sport, a.sample_path FROM activities a "
                       "LEFT JOIN activity_tracks t ON t.activity_id = a.id "
                       "WHERE t.activity_id IS NULL AND a.sample_path IS NOT NULL").fetchall()
    for aid, sub_sport, rel in rows:
        try:
            t, lat, lon = _read_positions(samples_dir, rel)
        except (OSError, ValueError, KeyError):
            continue  # samples missing or unreadable: skip, no row, so it is retried next scan
        _store_route(con, aid, sub_sport, t, lat, lon)


def _scan(con, cfg: Config, now: float | None, retry_failed: bool = False) -> ScanResult:
    now = time.time() if now is None else now
    result = ScanResult()
    _backfill_max_power(con, cfg.samples_dir)
    _backfill_routes(con, cfg.samples_dir)
    if not cfg.fit_dir.is_dir():
        result.folder_missing = True
        return result

    known = {p: (size, mtime) for p, size, mtime, status in
             con.execute("SELECT path, size, mtime, status FROM source_files").fetchall()
             if not (retry_failed and status == "failed")}
    for path in sorted(p for p in cfg.fit_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".fit"):
        st = path.stat()
        key = str(path)
        if known.get(key) == (st.st_size, st.st_mtime):
            result.unchanged += 1
            continue
        if now - st.st_mtime < MIN_AGE_SECONDS:
            result.deferred += 1
            continue
        try:
            status = _import_file(con, cfg, path)
        except Exception as e:  # one bad file must not stop the run
            status = "failed"
            reason = e.args[0] if isinstance(e, NotAnActivity) and e.args else f"{type(e).__name__}: {e}"
            result.failures.append((path.name, reason))
            con.execute("INSERT OR REPLACE INTO ingest_failures (path, reason) VALUES (?, ?)", [key, reason])
        else:
            con.execute("DELETE FROM ingest_failures WHERE path = ?", [key])
            if status == "imported":
                result.imported += 1
            else:
                result.duplicates += 1
        con.execute("INSERT OR REPLACE INTO source_files VALUES (?, ?, ?, ?)",
                    [key, st.st_size, st.st_mtime, status])
    return result


def _import_file(con, cfg: Config, path: Path) -> str:
    act = parse_fit(path)
    serial = act.serial or "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    start_utc = act.start_time.astimezone(timezone.utc).replace(tzinfo=None)
    if con.execute("SELECT 1 FROM activities WHERE start_time = ? AND device_serial = ?",
                   [start_utc, serial]).fetchone():
        return "duplicate"

    local_date = act.start_time.astimezone().date()
    score = score_activity(
        {"moving_seconds": act.moving_seconds, "normalized_power": act.normalized_power,
         "hr_histogram": act.hr_histogram},
        db.thresholds_on(con, local_date), act.sport, cfg.zone_edges)
    rel = sample_relpath(act.sport, act.start_time, serial)
    write_samples(cfg.samples_dir, rel, act.samples)  # before the row, so a row never lacks samples

    try:
        activity_id = con.execute(
            """INSERT INTO activities (start_time, local_date, device_serial, sport, sub_sport, source_path,
                   sample_path, elapsed_seconds, moving_seconds, distance_m, avg_hr, max_hr, avg_power,
                   max_power, normalized_power, hr_histogram, tss, tss_method, relative_effort, ftp_used, thr_hr_used,
                   max_hr_used, unscored_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [start_utc, local_date, serial, act.sport, act.sub_sport, str(path), rel, act.elapsed_seconds,
             act.moving_seconds, act.distance_m, act.avg_hr, act.max_hr, act.avg_power, act.max_power, act.normalized_power,
             json.dumps(act.hr_histogram) if act.hr_histogram else None,
             score["tss"], score["tss_method"], score["relative_effort"], score["ftp_used"], score["thr_hr_used"],
             score["max_hr_used"], score["unscored_reason"]]).fetchone()[0]
    except duckdb.ConstraintException:  # lost a race with another importer: it is a duplicate
        return "duplicate"
    _store_route(con, activity_id, act.sub_sport, act.samples["t"], act.samples["lat"], act.samples["lon"])
    return "imported"


def _store_route(con, activity_id: int, sub_sport, t, lat, lon) -> None:
    """Store the simplified route; a zero-point row marks activities with no usable GPS as handled."""
    segments, points = route_row(sub_sport, t, lat, lon)
    con.execute("INSERT OR IGNORE INTO activity_tracks VALUES (?, ?, ?)", [activity_id, segments, points])
