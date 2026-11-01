"""Per-activity 1 Hz samples stored as Parquet, partitioned by sport and year."""
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


def sample_relpath(sport: str, start: datetime, serial_key: str) -> str:
    """Deterministic from the dedupe key, so re-importing (or recovering from a crash) overwrites."""
    safe_sport = re.sub(r"[^A-Za-z0-9_-]", "_", sport)
    safe_key = re.sub(r"[^A-Za-z0-9_-]", "-", serial_key)[:40]
    return f"sport={safe_sport}/year={start:%Y}/{start:%Y%m%dT%H%M%S}_{safe_key}.parquet"


def write_samples(samples_dir: Path, relpath: str, df: pd.DataFrame) -> Path:
    """Write to a temp file then rename, so readers never see a partial file."""
    final = Path(samples_dir) / relpath
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, final)
    return final


def read_samples(samples_dir: Path, relpath: str) -> pd.DataFrame:
    return pd.read_parquet(Path(samples_dir) / relpath)
