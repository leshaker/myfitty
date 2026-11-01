import bisect

from myfitty.metrics.constants import DEFAULT_ZONE_FRACTIONS, RELATIVE_EFFORT_WEIGHTS


def default_zone_edges(max_hr: float | None) -> tuple[float, ...] | None:
    """Zone edges (upper bounds of Z1..Z4, in bpm) derived from max HR when none are configured."""
    return tuple(f * max_hr for f in DEFAULT_ZONE_FRACTIONS) if max_hr else None


def relative_effort(hr_histogram: dict | None, zone_edges) -> float | None:
    """Zone-weighted relative effort from {bpm: seconds}.

    zone_edges: four ascending bpm values; a heart rate at or above an edge belongs to the next zone.
    None when there is no heart rate data or no zones.
    """
    if not hr_histogram or not zone_edges:
        return None
    edges = sorted(zone_edges)
    total = 0.0
    for bpm, seconds in hr_histogram.items():
        total += RELATIVE_EFFORT_WEIGHTS[bisect.bisect_right(edges, float(bpm))] * float(seconds) / 60.0
    return total
