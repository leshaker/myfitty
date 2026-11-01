from myfitty.metrics.constants import TRIMP_ZONES


def trimp(hr_histogram: dict | None, max_hr: float | None) -> float | None:
    """Edwards TRIMP: minutes in each of five zones (50-100% of max HR) times weight 1-5."""
    if not hr_histogram or not max_hr:
        return None
    total = 0.0
    for bpm, seconds in hr_histogram.items():
        frac = float(bpm) / max_hr
        weight = 0
        for floor, w in TRIMP_ZONES:
            if frac >= floor:
                weight = w
        total += weight * float(seconds) / 60.0
    return total
