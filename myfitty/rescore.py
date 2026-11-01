"""Recompute stored scores from stored summaries when thresholds change."""
import json
from datetime import date

from myfitty import db
from myfitty.metrics.scoring import score_activity

SCORE_COLUMNS = ("tss", "tss_method", "trimp", "ftp_used", "thr_hr_used", "max_hr_used", "unscored_reason")


def rescore(con, start: date | None = None, end: date | None = None) -> int:
    """Rescore activities with start <= local_date < end (None = unbounded). Returns rows changed."""
    q = ("SELECT id, local_date, moving_seconds, normalized_power, hr_histogram, "
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
        aid, local_date, moving, npw, hist = row[:5]
        old = dict(zip(SCORE_COLUMNS, row[5:]))
        new = score_activity(
            {"moving_seconds": moving, "normalized_power": npw,
             "hr_histogram": json.loads(hist) if hist else None},
            db.thresholds_on(con, local_date))
        if new != old:
            con.execute(
                "UPDATE activities SET " + ", ".join(f"{c} = ?" for c in SCORE_COLUMNS) + " WHERE id = ?",
                [new[c] for c in SCORE_COLUMNS] + [aid])
            changed += 1
    return changed


def save_threshold(con, metric: str, effective_from: date, value: float) -> int:
    """Add/replace a threshold entry and rescore exactly the activities it affects."""
    start, end = db.set_threshold(con, metric, effective_from, value)
    return rescore(con, start, end)


def remove_threshold(con, metric: str, effective_from: date) -> int:
    rng = db.delete_threshold(con, metric, effective_from)
    return 0 if rng is None else rescore(con, *rng)
