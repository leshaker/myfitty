# Design

## Context

Every imported activity already keeps its 1 Hz samples, including `lat` and `lon`, in Parquet (`activities.sample_path`). Nothing reads positions yet. The page is a single Streamlit script (`app.py`) with shared sidebar filters (sport, date range) and cached query functions. `pydeck` (0.9.3, deck.gl for Python) ships with Streamlit, and `st.pydeck_chart` renders it. See proposal.md for motivation.

Measurements on the owner's real data (645 activities):

| Fact | Value |
|---|---|
| Activities with GPS / without | 615 / 30 (indoor, swimming, yoga) |
| Virtual rides with game-world GPS (lat −21.7, lon 167) | 30 (112,272 points) |
| Real outdoor activities | 585 (cycling about 420, running 104, hiking 27, walking 31) |
| Raw GPS points / route length | 2.8 million at 1 Hz / 17,382 km |
| Stretches after splitting at gaps (30 s no fix, or a 300 m jump) | 2,577, about 4.4 per activity |
| After thinning at 5 / 10 / 20 m | 145k / **93k** / 63k points (5.2% / **3.3%** / 2.2%) |
| Build time for the whole history | about 5 s (9 ms per activity) |
| Even 100 m sampling for density | 174k points (about 4 MB as JSON) |
| Raw 5 s points, for comparison | 584k points (about 15 MB) |

## Goals / Non-Goals

**Goals:**
- A map that reacts to a filter change within 3 seconds on the full history, sending under 5 MB to the browser.
- No false lines across GPS dropouts, and no fake game-world coordinates on the map.
- Routes available for activities imported before this change without re-reading FIT files.

**Non-Goals:**
- Hiding a radius around home (privacy zones), route detail for one activity, GPX/TCX activities, offline tiles.
- A custom map renderer: deck.gl through pydeck is enough.

## Decisions

**Store simplified routes in DuckDB, not as another Parquet set.** A table `activity_tracks(activity_id PRIMARY KEY, segments VARCHAR, point_count INTEGER)` holds each route as JSON, `[[[lon, lat], ...], ...]`, one inner list per continuous stretch, coordinates rounded to 5 decimals (about 1 m). The whole history is about 2.4 MB, it is read with a join on `activities` for the sport and date filters, and rows are small and mutable together with activities. Alternatives: reading the 1 Hz Parquet samples at query time (15 MB at 5 s spacing, plus gap handling on every filter change) and a second Parquet dataset (no benefit at this size). A row exists for every handled activity, with `point_count = 0` when there is no usable GPS, so the backfill never repeats work. The table is created by the existing `CREATE TABLE IF NOT EXISTS` schema, so no column migration is needed.

**Build routes in a pure module, `myfitty/ingest/tracks.py`.** Steps: drop rows without a position (and `(0, 0)` and out-of-range values); split into stretches wherever consecutive fixes are more than 30 s apart or more than 300 m apart; project to metres around the activity's mean latitude (equirectangular, accurate to well under a metre over a route); thin each stretch with iterative Douglas–Peucker at 10 m (numpy, no new dependency); drop stretches with fewer than two points. 10 m was chosen from the table: it keeps 3.3% of the points and the line is visually identical at city zoom; 5 m would add 55% more points for no visible gain. All three numbers are constants.

**Virtual rides are excluded by `sub_sport`.** The owner's 30 Zwift-style rides have `sub_sport = virtual_activity`; their route is never stored (`point_count = 0`). A location heuristic (for example a box around the game world) was rejected as brittle. Other platforms that write a different sub-sport would need a line added to the exclusion set in `constants`; that is a known limit.

**Compute routes at import, and backfill from the samples.** The importer already holds the 1 Hz samples in memory, so it builds the route right after inserting the activity (using `RETURNING id`). Activities imported earlier get theirs in the scan's backfill step, next to the maximum-power backfill: select activities with no `activity_tracks` row, read only `t`, `lat`, `lon` from their Parquet file, build and insert. A file that cannot be read is skipped without a row, so it is retried next scan (a cheap failed read). The backfill runs under `db.WRITE_LOCK` like the rest of the scan, and takes about 5 s for the owner's history.

**Queries.** `queries.routes(con, sport, start, end)` joins `activity_tracks` to `activities`, keeps `point_count > 0`, and returns one row per stretch with the sport, activity id and date. `geo.density_points(routes, spacing_m=100)` (pure) walks each stretch and emits points evenly by distance (cumulative distance plus `np.interp`), so each activity weighs by distance covered, not by time or recorded points. 100 m gives about 174k points for the full history, about 4 MB, inside the 5 MB budget; the constant can be raised if a larger history needs it. Both results are cached with `st.cache_data` like the other queries and cleared after an import.

**Map: two pydeck layers, one at a time.** Routes view is a `PathLayer` with `width_min_pixels` 1.5 and a low alpha (about 70 of 255), so overlapping lines add up like Strava's heatmap. When all sports are shown, each route gets its sport's colour from the same palette as the charts (cycling blue, running orange, hiking green, walking pink, anything else grey) and a one-line legend is drawn above the map. Density view is a `HeatmapLayer` (`aggregation="SUM"`, pixel radius about 25) over the evenly spaced points. Only the selected layer's data is sent. The viewport is computed in a pure function `geo.fit_view(bbox, width, height)` (Mercator zoom from the bounding box, a small margin, clamped between zoom 2 and 16) so it is testable; the same function refits when the filters change because the view state is recomputed on every run.

**Two pydeck details found while implementing.** (1) `pydeck` pretty-prints its JSON (`indent=2`), which put each coordinate on its own indented line: 132,000 density points came to 7.8 MB, against about 3 MB compact. Streamlit sends whatever `Deck.to_json()` returns, so `mapview.CompactDeck` overrides it to emit compact JSON; this is what keeps the payload inside the 5 MB budget. (2) `pydeck` treats plain strings as JavaScript expressions, so `aggregation="SUM"` was sent as `@@=SUM` and would have broken the layer; literal strings are wrapped in `pydeck.types.String`. Both were caught by `AppTest` on the deck JSON, not in a browser.

**Measured on the owner's full history (2019 to today, all sports).** Routes view: 0.29 s, 1.89 MB, 2,577 stretches, 93,513 vertices. Density view: 0.46 s on first compute (0.32 s when cached), 3.41 MB, 176,000 points. The map starts at about latitude 45.4, longitude 11.1, zoom 3.7 because the history spans Europe. Both are inside the 3 s and 5 MB budget. The backfill of all 645 activities took about 3 s.

**Basemap on by default, switchable.** `map_style` follows the Streamlit theme (Carto positron or dark-matter, no token needed). With the toggle off, `map_style=None`, so the map has no tile layer and no tile requests are made. This was checked with `AppTest`: the deck JSON carries a Carto style URL when on and none when off. The default is on because a bare line drawing is hard to read; the toggle exists because the tile server learns which area is on screen.

**Where it lives on the page.** A `st.segmented_control` at the top of the main area switches between Training and Heatmap, and only the active view is built and sent. Streamlit tabs were rejected: they render every tab on every rerun, so the 2–4 MB map payload would be re-sent each time the CTL/ATL pills were clicked. The sidebar sport and date filters apply to both views, as does the existing import button.

**Testing the map.** `AppTest` exposes the map as a `deck_gl_json_chart` element; its JSON gives the layer types, the data, the view state and the style, which is enough to check layers, filters, exclusions and the basemap switch without a browser. The segmented control is a `button_group` like the series pills, so the existing tests that pick `button_group` by index must look the pills up by key.

## Risks / Trade-offs

- [Thinning at 10 m rounds off tight switchbacks and roundabouts when zoomed all the way in] → The tolerance is a constant; 5 m costs 55% more points if it matters.
- [The gap thresholds (30 s, 300 m) were tuned on one person's data; auto-pause splits routes at every stop] → Intended: no line is drawn across a pause. Constants, covered by tests.
- [Virtual rides from other platforms may not use `sub_sport = virtual_activity`] → One entry in an exclusion set; the owner will see it as an odd stretch of map.
- [All-time view of a Europe-wide history is a thin scribble at the zoom that fits everything] → The filters narrow it, and the view refits; Density shows the overview better. The default date range stays the sidebar's (last 180 days), which suits the training charts; widening it is one control.
- [The first scan after upgrading takes about 5 s longer for the backfill] → One time only.
- [Basemap tiles reveal the viewed area to the tile provider] → The toggle; everything else stays on the machine.

## Open Questions

- Should the Heatmap view default to all time instead of the sidebar's range? This does not change the specs or the tasks: it is one default.
