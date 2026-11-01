"""Turn 1 Hz GPS samples into a simplified route: continuous stretches of [lon, lat] points."""
import json
import math

import numpy as np

from myfitty.metrics.constants import (NON_GEOGRAPHIC_SUB_SPORTS, TRACK_DECIMALS, TRACK_GAP_SECONDS,
                                       TRACK_JUMP_METRES, TRACK_TOLERANCE_METRES)


def _project(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Equirectangular projection to metres around the mean latitude (sub-metre error over a route)."""
    k = math.cos(math.radians(float(np.mean(lat))))
    return np.column_stack([lon * 111320.0 * k, lat * 110540.0])


def _distance_to_segment(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = b - a
    length2 = float(d @ d)
    if length2 == 0.0:
        return np.hypot(*(points - a).T)
    t = np.clip(((points - a) @ d) / length2, 0.0, 1.0)
    return np.hypot(*(points - (a + np.outer(t, d))).T)


def douglas_peucker(xy: np.ndarray, tolerance: float) -> np.ndarray:
    """Indices of the points to keep so no dropped point is further than `tolerance` from the line."""
    n = len(xy)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        dist = _distance_to_segment(xy[a + 1:b], xy[a], xy[b])
        i = int(np.argmax(dist))
        if dist[i] > tolerance:
            m = a + 1 + i
            keep[m] = True
            stack += [(a, m), (m, b)]
    return np.flatnonzero(keep)


def build_stretches(t, lat, lon, *, gap_seconds=TRACK_GAP_SECONDS, jump_metres=TRACK_JUMP_METRES,
                    tolerance=TRACK_TOLERANCE_METRES, decimals=TRACK_DECIMALS) -> list[list[list[float]]]:
    """Simplified route as a list of continuous stretches, each a list of [lon, lat].

    Rows without a valid position are dropped; the route is split where fixes are more than
    `gap_seconds` or `jump_metres` apart, so nothing is ever drawn across a GPS dropout.
    """
    t, lat, lon = (np.asarray(a, dtype=float) for a in (t, lat, lon))
    valid = (np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
             & ~((lat == 0) & (lon == 0)))
    t, lat, lon = t[valid], lat[valid], lon[valid]
    if len(t) < 2:
        return []
    xy = _project(lat, lon)
    step = np.hypot(*np.diff(xy, axis=0).T)
    breaks = np.flatnonzero((np.diff(t) > gap_seconds) | (step > jump_metres)) + 1
    stretches = []
    for lo, hi in zip(np.concatenate([[0], breaks]), np.concatenate([breaks, [len(t)]])):
        if hi - lo < 2:
            continue
        kept = lo + douglas_peucker(xy[lo:hi], tolerance)
        stretches.append([[round(float(lon[i]), decimals), round(float(lat[i]), decimals)] for i in kept])
    return stretches


def route_row(sub_sport: str | None, t, lat, lon) -> tuple[str, int]:
    """(segments JSON, point count) to store for an activity; virtual rides never get a route."""
    if sub_sport in NON_GEOGRAPHIC_SUB_SPORTS:
        return "[]", 0
    stretches = build_stretches(t, lat, lon)
    return json.dumps(stretches, separators=(",", ":")), sum(len(s) for s in stretches)
