"""Map geometry helpers (pure): evenly spaced points along routes, and a viewport that fits a box."""
import math

import numpy as np

TILE = 512          # deck.gl world width in pixels at zoom 0
MIN_ZOOM, MAX_ZOOM = 2.0, 16.0
MARGIN_ZOOM = 0.3   # zoom out a little so routes do not touch the edge


def density_points(stretches, spacing_m: float) -> np.ndarray:
    """Points evenly spaced by distance along each stretch, as an (N, 2) array of [lon, lat].

    Each stretch contributes its two ends plus a point every `spacing_m`, so every activity weighs
    by the distance it covers, not by how long it took or how many fixes it recorded.
    """
    out = []
    for stretch in stretches:
        pts = np.asarray(stretch, dtype=float)
        if len(pts) == 0:
            continue
        k = math.cos(math.radians(float(pts[:, 1].mean())))
        xy = np.column_stack([pts[:, 0] * 111320.0 * k, pts[:, 1] * 110540.0])
        cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
        total = cum[-1]
        marks = np.arange(0.0, total, spacing_m)
        if total > 0:
            marks = np.append(marks, total)
        else:
            marks = np.array([0.0])
        x = np.interp(marks, cum, xy[:, 0])
        y = np.interp(marks, cum, xy[:, 1])
        out.append(np.column_stack([x / (111320.0 * k), y / 110540.0]))
    return np.vstack(out) if out else np.empty((0, 2))


def _merc_y(lat: float) -> float:
    """Mercator y as a fraction of the world height (0 at the top)."""
    lat = max(min(lat, 85.0511), -85.0511)
    return 0.5 - math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) / (2 * math.pi)


def _merc_lat(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp((0.5 - y) * 2 * math.pi)) - math.pi / 2)


def fit_view(bbox, width: int = 1000, height: int = 600) -> tuple[float, float, float]:
    """(longitude, latitude, zoom) of a map `width` x `height` px that contains `bbox`.

    bbox is (lon_min, lat_min, lon_max, lat_max). Zoom is clamped to [2, 16]; a point or a tiny
    box therefore gets the maximum zoom.
    """
    lon0, lat0, lon1, lat1 = bbox
    lon_frac = (lon1 - lon0) / 360.0
    y_top, y_bottom = _merc_y(lat1), _merc_y(lat0)
    lat_frac = y_bottom - y_top
    zooms = []
    if lon_frac > 0:
        zooms.append(math.log2(width / (TILE * lon_frac)))
    if lat_frac > 0:
        zooms.append(math.log2(height / (TILE * lat_frac)))
    zoom = min(zooms) - MARGIN_ZOOM if zooms else MAX_ZOOM
    zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
    return (lon0 + lon1) / 2.0, _merc_lat((y_top + y_bottom) / 2.0), zoom


def bounding_box(stretches):
    """(lon_min, lat_min, lon_max, lat_max) of all stretches, or None when there are none."""
    pts = [np.asarray(s, dtype=float) for s in stretches if len(s)]
    if not pts:
        return None
    all_pts = np.vstack(pts)
    return (float(all_pts[:, 0].min()), float(all_pts[:, 1].min()),
            float(all_pts[:, 0].max()), float(all_pts[:, 1].max()))
