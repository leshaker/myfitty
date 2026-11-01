"""Scan a folder of FIT files and import new activities."""
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path

from myfitty import db
from myfitty.config import Config, load_config
from myfitty.ingest.parser import NotAnActivity, parse_fit
from myfitty.ingest.samples import sample_relpath, write_samples
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


def scan(con, cfg: Config | None = None, now: float | None = None) -> ScanResult:
    """Import every new or changed `.fit` file under the configured folder (which is only read)."""
    cfg = cfg or load_config()
    now = time.time() if now is None else now
    result = ScanResult()
    if not cfg.fit_dir.is_dir():
        result.folder_missing = True
        return result

    known = {p: (size, mtime) for p, size, mtime in
             con.execute("SELECT path, size, mtime FROM source_files").fetchall()}
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
        db.thresholds_on(con, local_date), act.sport)
    rel = sample_relpath(act.sport, act.start_time, serial)
    write_samples(cfg.samples_dir, rel, act.samples)  # before the row, so a row never lacks samples

    con.execute(
        """INSERT INTO activities (start_time, local_date, device_serial, sport, sub_sport, source_path,
               sample_path, elapsed_seconds, moving_seconds, distance_m, avg_hr, max_hr, avg_power,
               normalized_power, hr_histogram, tss, tss_method, trimp, ftp_used, thr_hr_used,
               max_hr_used, unscored_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [start_utc, local_date, serial, act.sport, act.sub_sport, str(path), rel, act.elapsed_seconds,
         act.moving_seconds, act.distance_m, act.avg_hr, act.max_hr, act.avg_power, act.normalized_power,
         json.dumps(act.hr_histogram) if act.hr_histogram else None,
         score["tss"], score["tss_method"], score["trimp"], score["ftp_used"], score["thr_hr_used"],
         score["max_hr_used"], score["unscored_reason"]])
    return "imported"
