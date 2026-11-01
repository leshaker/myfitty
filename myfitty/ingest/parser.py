"""Parse one FIT file into an activity summary plus 1 Hz samples."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from struct import error as struct_error

import fitdecode
import numpy as np
import pandas as pd

from myfitty.metrics.tss import normalized_power

SAMPLE_COLUMNS = ["t", "hr", "power", "speed", "lat", "lon", "altitude"]
_SEMICIRCLE_TO_DEG = 180.0 / 2 ** 31


class FitParseError(Exception):
    """The file could not be decoded."""


class NotAnActivity(FitParseError):
    """A valid FIT file with no session message (settings, monitoring, ...)."""


@dataclass
class ParsedActivity:
    start_time: datetime            # UTC, timezone-aware
    serial: str | None
    sport: str
    sub_sport: str | None
    elapsed_seconds: float | None
    moving_seconds: float | None
    distance_m: float | None
    avg_hr: float | None
    max_hr: float | None
    avg_power: float | None
    max_power: float | None
    normalized_power: float | None
    hr_histogram: dict[int, int]
    samples: pd.DataFrame


def _enum_name(v) -> str | None:
    return None if v is None else str(v)


def _scalar(v):
    """Some devices write several samples per record (array fields, e.g. enhanced_speed): take the latest."""
    if isinstance(v, (list, tuple)):
        v = next((x for x in reversed(v) if x is not None), None)
    return v


def _first(frame, *names):
    for n in names:
        if frame.has_field(n):
            v = _scalar(frame.get_value(n, fallback=None))
            if v is not None:
                return v
    return None


def _as_utc(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def parse_fit(path: str | Path) -> ParsedActivity:
    records, session, serial, first_ts = [], None, None, None
    try:
        with fitdecode.FitReader(str(path)) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name == "file_id" and serial is None:
                    serial = _first(frame, "serial_number")
                elif frame.name == "device_info" and serial is None:
                    serial = _first(frame, "serial_number")
                elif frame.name == "record":
                    ts = _as_utc(_first(frame, "timestamp"))
                    if ts is None:
                        continue
                    first_ts = first_ts or ts
                    records.append((
                        ts,
                        _first(frame, "heart_rate"),
                        _first(frame, "power"),
                        _first(frame, "enhanced_speed", "speed"),
                        _first(frame, "position_lat"),
                        _first(frame, "position_long"),
                        _first(frame, "enhanced_altitude", "altitude"),
                        _first(frame, "distance"),
                    ))
                elif frame.name == "session" and session is None:
                    session = frame
    except fitdecode.FitError as e:
        raise FitParseError(f"cannot decode FIT file: {e}") from e
    except (OSError, ValueError, struct_error) as e:
        raise FitParseError(f"cannot read FIT file: {e}") from e

    if session is None:
        raise NotAnActivity("not an activity (no session message)")

    start = _as_utc(_first(session, "start_time")) or first_ts
    if start is None:
        raise FitParseError("activity has no start time")

    samples = _resample(records)
    hr = samples["hr"].dropna()
    pw = samples["power"]
    has_power = pw.notna().any()
    elapsed = _first(session, "total_elapsed_time")
    moving = _first(session, "total_timer_time")
    distance = _first(session, "total_distance")
    if distance is None and records and records[-1][7] is not None:
        distance = records[-1][7]

    return ParsedActivity(
        start_time=start.replace(microsecond=0),
        serial=str(serial) if serial is not None else None,
        sport=_enum_name(_first(session, "sport")) or "unknown",
        sub_sport=_enum_name(_first(session, "sub_sport")),
        elapsed_seconds=float(elapsed) if elapsed is not None else None,
        moving_seconds=float(moving) if moving is not None else (float(len(samples)) if len(samples) else None),
        distance_m=float(distance) if distance is not None else None,
        avg_hr=float(hr.mean()) if len(hr) else None,
        max_hr=float(hr.max()) if len(hr) else None,
        avg_power=float(pw.fillna(0).mean()) if has_power else None,
        max_power=float(pw.max()) if has_power else None,
        normalized_power=normalized_power(pw.to_numpy()) if has_power else None,
        hr_histogram={int(b): int(n) for b, n in hr.astype(int).value_counts().sort_index().items()},
        samples=samples,
    )


def _resample(records) -> pd.DataFrame:
    """One row per second from the first to the last record; seconds without a record stay NaN."""
    if not records:
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in SAMPLE_COLUMNS})
    df = pd.DataFrame(records, columns=["ts", "hr", "power", "speed", "lat", "lon", "altitude", "distance"])
    df["t"] = df["ts"].map(lambda d: int(d.timestamp()))
    df = df.drop(columns=["ts", "distance"]).groupby("t").last()
    df = df.reindex(np.arange(df.index.min(), df.index.max() + 1)).astype("float64")
    df["lat"] *= _SEMICIRCLE_TO_DEG
    df["lon"] *= _SEMICIRCLE_TO_DEG
    df.index.name = "t"
    return df.reset_index()[SAMPLE_COLUMNS].astype({"t": "int64"})

