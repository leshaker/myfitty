import math

import numpy as np
import pytest

from myfitty import geo


def metres(a, b):
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((b[0] - a[0]) * 111320 * k, (b[1] - a[1]) * 110540)


def test_spacing_and_total_length_are_preserved():
    stretch = [[8.0, 48.0], [8.0, 48.01], [8.01, 48.01]]               # ~1.1 km north, then ~0.75 km east
    pts = geo.density_points([stretch], 100)
    gaps = [metres(a, b) for a, b in zip(pts[:-1], pts[1:])]
    assert max(gaps) <= 100.5 and min(gaps) > 0
    assert sum(gaps) == pytest.approx(metres(stretch[0], stretch[1]) + metres(stretch[1], stretch[2]), rel=0.01)
    assert tuple(pts[0]) == pytest.approx((8.0, 48.0)) and tuple(pts[-1]) == pytest.approx((8.01, 48.01))


def test_short_stretch_keeps_both_endpoints_and_empty_input_is_empty():
    pts = geo.density_points([[[8.0, 48.0], [8.0003, 48.0]]], 100)      # ~22 m
    assert len(pts) == 2
    assert geo.density_points([], 100).shape == (0, 2)
    assert len(geo.density_points([[[8.0, 48.0]]], 100)) == 1


def test_every_activity_weighs_by_distance_not_by_point_count():
    sparse = [[8.0, 48.0], [8.0, 48.01]]                                 # two fixes, 1.1 km
    dense = [[8.1, 48.0 + 0.01 * i / 1000] for i in range(1001)]         # a thousand fixes, the same length
    a, b = geo.density_points([sparse], 100), geo.density_points([dense], 100)
    assert abs(len(a) - len(b)) <= 1


def inside(view, bbox, width, height):
    lon, lat, zoom = view
    scale = geo.TILE * 2 ** zoom
    cx, cy = (lon + 180) / 360, geo._merc_y(lat)
    for lo, la in [(bbox[0], bbox[1]), (bbox[2], bbox[3])]:
        dx = abs(((lo + 180) / 360 - cx) * scale)
        dy = abs((geo._merc_y(la) - cy) * scale)
        if dx > width / 2 or dy > height / 2:
            return False
    return True


@pytest.mark.parametrize("bbox", [(7.7, 47.9, 8.0, 48.1), (-3.0, 40.0, 25.0, 55.0), (13.3, 52.4, 13.5, 52.6),
                                  (7.0, 47.0, 7.2, 50.0)])
@pytest.mark.parametrize("size", [(1000, 600), (600, 1000), (1400, 400)])
def test_view_contains_the_box_at_several_aspect_ratios(bbox, size):
    view = geo.fit_view(bbox, *size)
    assert inside(view, bbox, *size)
    assert 2 <= view[2] <= 16
    assert bbox[0] <= view[0] <= bbox[2] and bbox[1] <= view[1] <= bbox[3]


def test_point_or_tiny_box_gets_maximum_zoom_and_huge_box_the_minimum():
    assert geo.fit_view((8.0, 48.0, 8.0, 48.0))[2] == 16
    assert geo.fit_view((8.0, 48.0, 8.0001, 48.0001))[2] == 16
    assert geo.fit_view((-170, -60, 170, 70))[2] == 2


def test_bounding_box():
    assert geo.bounding_box([]) is None
    assert geo.bounding_box([[[8.0, 48.0], [8.2, 48.1]], [[7.9, 48.3]]]) == (7.9, 48.0, 8.2, 48.3)
