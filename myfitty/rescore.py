"""Recompute stored scores from stored summaries when thresholds change."""
import json
from datetime import date

from myfitty import db
from myfitty.config import ConfigError, load_config
from myfitty.metrics.scoring import score_activity

SCORE_COLUMNS = ("tss", "tss_method", "relative_effort", "ftp_used", "thr_hr_used", "max_hr_used", "unscored_reason")


def rescore(con, start: date | None = None, end: date | None = None, zone_edges=None) -> int:
    """Rescore activities with start <= local_date < end (None = unbounded). Returns rows changed."""
    with db.WRITE_LOCK:
        return _rescore(con, start, end, zone_edges)


def _configured_zone_edges():
    try:
        return load_config().zone_edges
    except ConfigError:
        return None


def _rescore(con, start, end, zone_edges) -> int:
    if zone_edges is None:
        zone_edges = _configured_zone_edges()
    q = ("SELECT id, local_date, sport, moving_seconds, normalized_power, hr_histogram, "
         + ", ".join(SCORE_COLUMNS) + " FROM activities WHERE true")
    args = []
    if start is not None:
        q += " AND local_date >= ?"
        args.append(start)
    if end is not None:
        q += " AND local_date < ?"
        args.append(end)
    changed = 0
    for row in con.execute(q, args).fetchall():
        aid, local_date, sport, moving, npw, hist = row[:6]
        old = dict(zip(SCORE_COLUMNS, row[6:]))
        new = score_activity(
            {"moving_seconds": moving, "normalized_power": npw,
             "hr_histogram": json.loads(hist) if hist else None},
            db.thresholds_on(con, local_date), sport, zone_edges)
        if new != old:
            con.execute(
                "UPDATE activities SET " + ", ".join(f"{c} = ?" for c in SCORE_COLUMNS) + " WHERE id = ?",
                [new[c] for c in SCORE_COLUMNS] + [aid])
            changed += 1
    return changed


def save_threshold(con, metric: str, effective_from: date, value: float) -> int:
    """Add/replace a threshold entry and rescore exactly the activities it affects."""
    with db.WRITE_LOCK:
        start, end = db.set_threshold(con, metric, effective_from, value)
        return rescore(con, start, end)


def remove_threshold(con, metric: str, effective_from: date) -> int:
    with db.WRITE_LOCK:
        rng = db.delete_threshold(con, metric, effective_from)
        return 0 if rng is None else rescore(con, *rng)


def seed_thresholds(con, entries) -> int:
    """Insert configured threshold entries that are not yet in the database, and rescore.

    Existing entries (including ones edited in the UI) are never overwritten or deleted, so the
    config file only fills gaps. Returns the number of entries added. Raises ValueError if an
    entry is invalid against what is already stored.
    """
    added = 0
    for e in entries:  # each save takes the write lock; a concurrent seeder just finds the entry present
        exists = con.execute("SELECT 1 FROM threshold_entries WHERE metric = ? AND effective_from = ?",
                             [e.metric, e.effective_from]).fetchone()
        if not exists:
            save_threshold(con, e.metric, e.effective_from, e.value)
            added += 1
    return added
