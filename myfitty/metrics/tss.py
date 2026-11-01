import numpy as np

from myfitty.metrics.constants import HR_TSS_ZONES, NP_WINDOW_SECONDS


def normalized_power(power_1hz) -> float | None:
    """NP from a 1 Hz power series (NaN counts as zero). None if under 30 s of data."""
    p = np.nan_to_num(np.asarray(power_1hz, dtype=float))
    if len(p) < NP_WINDOW_SECONDS:
        return None
    rolling = np.convolve(p, np.ones(NP_WINDOW_SECONDS) / NP_WINDOW_SECONDS, mode="valid")
    return float(np.mean(rolling ** 4) ** 0.25)


def power_tss(np_watts: float | None, ftp: float | None, seconds: float | None):
    """Return (tss, intensity_factor), or (None, None) when an input is missing."""
    if not np_watts or not ftp or not seconds:
        return None, None
    if_ = np_watts / ftp
    return (seconds / 3600.0) * if_ ** 2 * 100.0, if_


def hr_tss(hr_histogram: dict | None, threshold_hr: float | None) -> float | None:
    """hrTSS from {bpm: seconds}: each zone (fraction of threshold HR) scores a fixed TSS/hour."""
    if not hr_histogram or not threshold_hr:
        return None
    total = 0.0
    for bpm, seconds in hr_histogram.items():
        frac = float(bpm) / threshold_hr
        rate = next(r for upper, r in HR_TSS_ZONES if frac < upper)
        total += rate * float(seconds) / 3600.0
    return total
