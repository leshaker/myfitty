"""Build the heatmap's deck.gl map (pydeck). No Streamlit imports: app.py renders what this builds."""
import json

import numpy as np
import pydeck as pdk
from pydeck.types import String

from myfitty import geo
from myfitty.metrics.constants import DENSITY_SPACING_METRES

# Same hues as the charts' palette (cycling blue, running orange) plus green and pink for the other sports.
SPORT_COLORS = {"cycling": (42, 120, 214), "running": (235, 104, 52), "hiking": (27, 175, 122),
                "walking": (232, 123, 164)}
OTHER_COLOR = (130, 130, 130)
ROUTE_ALPHA = 70           # of 255: thin, translucent lines so overlapping routes add up
# An empty map style, as a data: URL because Streamlit's frontend calls string methods on mapStyle.
BLANK_STYLE = "data:application/json," + json.dumps({"version": 8, "sources": {}, "layers": []},
                                                    separators=(",", ":"))
MODES = ("Routes", "Density")


class CompactDeck(pdk.Deck):
    """pydeck pretty-prints its JSON (indent=2), which more than doubles the size of point data
    (7.8 MB instead of about 3 MB for 130,000 points). Streamlit sends whatever `to_json` returns.

    With `blank`, the style is an empty map style: without a mapStyle Streamlit falls back to its
    themed tile basemap, and pydeck refuses a custom style, so it is put in the JSON here.
    """

    def __init__(self, *args, blank: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.blank = blank

    def to_json(self):
        spec = json.loads(super().to_json())
        if self.blank:
            spec["mapStyle"] = BLANK_STYLE
        return json.dumps(spec, separators=(",", ":"))


def sport_color(sport: str) -> tuple[int, int, int]:
    return SPORT_COLORS.get(sport, OTHER_COLOR)


def legend(sports) -> list[tuple[str, str]]:
    """(sport, hex colour) for each sport present, in a stable order."""
    return [(s, "#%02x%02x%02x" % sport_color(s)) for s in sorted(set(sports))]


def density_data(stretches) -> list[list[float]]:
    """Evenly spaced [lon, lat] points (5 decimals) for the density layer."""
    return np.round(geo.density_points(stretches, DENSITY_SPACING_METRES), 5).tolist()


def build_deck(routes, mode: str, basemap: str | None, density=None, width: int = 1100,
               height: int = 600) -> pdk.Deck:
    """Deck for the routes (a DataFrame from queries.routes) in the given mode.

    basemap is "light" or "dark", or None for a plain background with no tiles. `density` is the
    precomputed result of `density_data` (so callers can cache it); only the selected layer's data is sent.
    """
    stretches = routes["stretch"].tolist()
    if mode == "Density":
        layer = pdk.Layer("HeatmapLayer", data=density if density is not None else density_data(stretches),
                          get_position="d", aggregation=String("SUM"), radius_pixels=25, intensity=1, threshold=0.05)
    else:
        data = [{"path": s, "color": [*sport_color(sp), ROUTE_ALPHA]}
                for s, sp in zip(stretches, routes["sport"])]
        layer = pdk.Layer("PathLayer", data=data, get_path="path", get_color="color", get_width=3,
                          width_min_pixels=1.5, pickable=False)
    lon, lat, zoom = geo.fit_view(geo.bounding_box(stretches), width, height)
    return CompactDeck(layers=[layer], initial_view_state=pdk.ViewState(longitude=lon, latitude=lat, zoom=zoom),
                    map_style=basemap, blank=basemap is None)
