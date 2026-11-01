import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    fit_dir: Path
    db_path: Path
    samples_dir: Path


def load_config() -> Config:
    """Read settings from the environment on every call, so tests can override them."""
    return Config(
        fit_dir=Path(os.environ.get("MYFITTY_FIT_DIR", "./fit")).expanduser(),
        db_path=Path(os.environ.get("MYFITTY_DB", "./data/myfitty.duckdb")).expanduser(),
        samples_dir=Path(os.environ.get("MYFITTY_SAMPLES_DIR", "./data/samples")).expanduser(),
    )
