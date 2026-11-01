import math

import numpy as np
import pytest

from myfitty.ingest import tracks

K = 111320.0 * math.cos(math.radians(48.0))      # metres per degree of longitude at 48 N
M = 110540.0                                      # metres per degree of latitude


def line(n, dlat=0.0001, dlon=0.0):
    """n fixes one second apart, moving by (dlat, dlon) degrees per second from (48, 8)."""
    i = np.arange(n)
    return i, 48.0 + dlat * i, 8.0 + dlon * i


def point_to_path_distance(p, path):
    best = np.inf
    for a, b in zip(path[:-1], path[1:]):
        d = b - a
        t = 0.0 if not d.any() else float(np.clip((p - a) @ d / (d @ d), 0, 1))
        best = min(best, float(np.hypot(*(p - (a + t * d)))))
    return best


def test_straight_line_collapses_to_its_ends():
    t, lat, lon = line(500)
    (s,) = tracks.build_stretches(t, lat, lon)
    assert len(s) == 2 and s[0] == [8.0, 48.0] and s[-1][1] == pytest.approx(48.0 + 0.0001 * 499, abs=1e-5)


def test_corner_is_kept():
    t = np.arange(200)
    lat = np.concatenate([48.0 + 0.0001 * np.arange(100), np.full(100, 48.0 + 0.0099)])
    lon = np.concatenate([np.full(100, 8.0), 8.0 + 0.0001 * np.arange(1, 101)])
    (s,) = tracks.build_stretches(t, lat, lon)
    assert len(s) == 3 and s[1][1] == pytest.approx(48.0099, abs=1e-5)


def test_no_original_point_further_than_the_tolerance_from_the_thinned_route():
    rng = np.random.default_rng(7)
    n = 3000
    lat = 48.0 + np.cumsum(rng.normal(0, 3e-5, n))
    lon = 8.0 + np.cumsum(rng.normal(0, 3e-5, n))
    t = np.arange(n)
    (s,) = tracks.build_stretches(t, lat, lon, jump_metres=10_000, decimals=8)
    assert len(s) < n / 4                                        # genuinely thinned
    path = np.array([[x * K, y * M] for x, y in s])
    xy = np.column_stack([lon * K, lat * M])
    assert max(point_to_path_distance(p, path) for p in xy) <= 10.5   # 10 m plus projection rounding


def test_gap_in_time_splits():
    t, lat, lon = line(300)
    t = np.where(t >= 100, t + 90, t)                            # 90 s with no fix after the 100th point
    lat = lat.copy()
    stretches = tracks.build_stretches(t, lat, lon, jump_metres=10_000)
    assert len(stretches) == 2


def test_jump_in_position_splits():
    t = np.arange(200)
    lat = np.where(t < 100, 48.0 + 1e-5 * t, 48.0 + 0.004 + 1e-5 * t)    # a 440 m jump at t = 100
    lon = np.full(200, 8.0)
    stretches = tracks.build_stretches(t, lat, lon)
    assert len(stretches) == 2


def test_pause_without_fixes_does_not_join_the_two_halves():
    t = np.concatenate([np.arange(100), np.arange(100) + 700])    # recording paused for ten minutes
    lat = np.concatenate([48.0 + 1e-5 * np.arange(100)] * 2)
    lon = np.full(200, 8.0)
    assert len(tracks.build_stretches(t, lat, lon)) == 2


def test_invalid_positions_are_dropped():
    t = np.arange(6, dtype=float)
    lat = np.array([48.0, np.nan, 0.0, 95.0, 48.0003, 48.0006])
    lon = np.array([8.0, 8.0, 0.0, 8.0, 8.0, 8.0])
    out = tracks.build_stretches(t, lat, lon, gap_seconds=1000)
    flat = [p for s in out for p in s]
    assert [8.0, 48.0] in flat and all(p[1] < 90 and p != [0.0, 0.0] for p in flat)


def test_single_fix_and_empty_input_give_no_stretches():
    assert tracks.build_stretches([], [], []) == []
    assert tracks.build_stretches([0], [48.0], [8.0]) == []
    assert tracks.build_stretches([0, 1], [np.nan, np.nan], [np.nan, np.nan]) == []


def test_coordinates_are_rounded_to_five_decimals():
    t, lat, lon = line(50, dlat=0.000123456, dlon=0.000234567)
    for lo, la in tracks.build_stretches(t, lat, lon)[0]:
        assert lo == round(lo, 5) and la == round(la, 5)
