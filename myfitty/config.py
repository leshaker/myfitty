import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from myfitty.db import METRICS

CONFIG_FILE = "myfitty.toml"


class ConfigError(ValueError):
    """The config file is unreadable or invalid."""


@dataclass(frozen=True)
class ThresholdEntry:
    metric: str
    effective_from: date
    value: float


@dataclass(frozen=True)
class Config:
    fit_dir: Path
    db_path: Path
    samples_dir: Path
    thresholds: tuple[ThresholdEntry, ...] = ()
    zone_edges: tuple[float, ...] | None = None   # HR zone edges for relative effort (bpm), else from max HR


def config_path() -> Path | None:
    """`MYFITTY_CONFIG` if set (must exist), else ./myfitty.toml if present, else None."""
    env = os.environ.get("MYFITTY_CONFIG")
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            raise ConfigError(f"MYFITTY_CONFIG points to a missing file: {p}")
        return p
    p = Path(CONFIG_FILE)
    return p if p.is_file() else None


def _read_thresholds(raw) -> tuple[ThresholdEntry, ...]:
    if not isinstance(raw, list):
        raise ConfigError("`thresholds` must be an array of tables: [[thresholds]]")
    out = []
    for i, t in enumerate(raw, 1):
        where = f"thresholds entry {i}"
        if not isinstance(t, dict) or not {"metric", "from", "value"} <= t.keys():
            raise ConfigError(f"{where}: needs metric, from and value")
        if t["metric"] not in METRICS:
            raise ConfigError(f"{where}: unknown metric {t['metric']!r}; expected one of {METRICS}")
        d = t["from"]
        try:
            d = d if isinstance(d, date) else date.fromisoformat(str(d))
        except ValueError:
            raise ConfigError(f"{where}: `from` must be a date like 2026-01-31, got {t['from']!r}") from None
        v = t["value"]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not v > 0:
            raise ConfigError(f"{where}: value must be a positive number, got {v!r}")
        out.append(ThresholdEntry(t["metric"], d, float(v)))
    return tuple(sorted(out, key=lambda e: (e.effective_from, e.metric)))


def _read_zone_edges(section) -> tuple[float, ...] | None:
    if section is None:
        return None
    raw = section.get("zone_edges") if isinstance(section, dict) else None
    if raw is None:
        return None
    ok = (isinstance(raw, list) and len(raw) == 4
          and all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in raw)
          and all(a < b for a, b in zip(raw, raw[1:])))
    if not ok:
        raise ConfigError("relative_effort.zone_edges must be four ascending positive bpm values, "
                          f"e.g. [114, 146, 153, 163]; got {raw!r}")
    return tuple(float(v) for v in raw)


def load_config() -> Config:
    """Settings from the environment and the optional TOML file, re-read on every call.

    Precedence for folders: environment variable > config file > built-in default.
    Relative paths in the file are relative to the file's own folder.
    """
    file_values: dict = {}
    base = Path(".")
    path = config_path()
    if path is not None:
        try:
            file_values = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise ConfigError(f"cannot read {path}: {e}") from e
        base = path.parent

    def folder(env_name: str, key: str, default: str) -> Path:
        if os.environ.get(env_name):
            return Path(os.environ[env_name]).expanduser()
        if key in file_values:
            p = Path(str(file_values[key])).expanduser()
            return p if p.is_absolute() else base / p
        return Path(default)

    return Config(
        fit_dir=folder("MYFITTY_FIT_DIR", "fit_dir", "./fit"),
        db_path=folder("MYFITTY_DB", "db_path", "./data/myfitty.duckdb"),
        samples_dir=folder("MYFITTY_SAMPLES_DIR", "samples_dir", "./data/samples"),
        thresholds=_read_thresholds(file_values.get("thresholds", [])),
        zone_edges=_read_zone_edges(file_values.get("relative_effort")),
    )
