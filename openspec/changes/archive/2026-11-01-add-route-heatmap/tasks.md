# Tasks

## 1. Route building (pure code)

- [x] 1.1 Add `myfitty/ingest/tracks.py` that turns 1 Hz samples into stretches: drop rows without a valid position (including `(0, 0)` and out-of-range values), split where fixes are more than 30 s or 300 m apart, project to metres around the activity's mean latitude, thin each stretch with Douglas–Peucker at 10 m, round to 5 decimals and drop stretches under two points; keep the thresholds in `metrics/constants.py`. Verify unit tests: a straight line collapses to its two ends, a corner is kept, no original point lies more than 10 m from the thinned line on a random walk, a 90 s gap and a 400 m jump each split, invalid positions are dropped, and an empty input gives no stretches
- [x] 1.2 Add `myfitty/geo.py` with `density_points(stretches, spacing_m)` (points evenly spaced by distance along each stretch) and `fit_view(bbox, width, height)` (centre and Mercator zoom containing a bounding box, clamped to 2–16). Verify unit tests: spacing and total length are preserved, a stretch shorter than the spacing still yields its endpoints, the view contains the box at several aspect ratios, and a single point or a tiny box gives the maximum zoom

## 2. Storage and backfill

- [x] 2.1 Add the `activity_tracks` table (`activity_id`, `segments` JSON, `point_count`) to the schema, build the route when an activity is imported (using `INSERT ... RETURNING id`), store a zero-point row for activities with no usable GPS, and never store a route for sub-sport `virtual_activity` (set in `constants`). Add `virtual_activity` support and a GPS-bearing option to the test generator. Verify importer tests: the outdoor fixture has a route with far fewer points than its samples, the indoor fixture has a zero-point row and is not reported as a failure, a virtual-ride fixture with GPS has no route, and a gap in the fixture produces two stretches
- [x] 2.2 Backfill routes in the scan for activities that have samples but no `activity_tracks` row, reading only `t`, `lat` and `lon` from the Parquet file, under the existing write lock. Verify tests: a database without routes gets them without any FIT file being read, a second scan does no further work (the Parquet reader is not called), an unreadable samples file is skipped without failing the scan, and the 0-point rows for no-GPS and virtual activities count as handled

## 3. Queries

- [x] 3.1 Add `queries.routes(con, sport, start, end)` returning one row per stretch with the sport, activity id, date and coordinates, filtered by sport and local date and excluding zero-point rows. Verify tests: sport filter, date filter, virtual and indoor activities absent, several stretches per activity, and an empty database

## 4. Heatmap view

- [x] 4.1 Add a Training / Heatmap `st.segmented_control` at the top of the main area so only the active view is built, and update the existing tests that pick the series pills by index to look them up by key. Verify an `AppTest` that the Training view renders as before with no map element, and the Heatmap view renders no training charts
- [x] 4.2 Build the Routes view: a `PathLayer` with thin translucent lines, sport colours from the chart palette and a legend when all sports are shown, one colour for a single sport. Verify `AppTest` checks on the deck JSON: layer type, low alpha, colours per sport and the legend, the sport and date filters change the routes, and a virtual ride's coordinates are absent
- [x] 4.3 Build the Density view: a `HeatmapLayer` over `geo.density_points` at 100 m, switchable with Routes while keeping the sport and date selection. Verify an `AppTest` that switching changes the layer type and keeps the filters, and that the point count equals the evenly spaced total
- [x] 4.4 Fit the view to the selection with `geo.fit_view`, add the basemap toggle (`map_style` follows the Streamlit theme, `None` when off) and the empty-state messages. Verify `AppTest` checks: the view contains every route and moves when the date range moves the routes to another region, the deck JSON has no map style with the toggle off, an indoor-only range shows the no-routes message and no map, and an empty database shows the usual empty state

## 5. Documentation

- [x] 5.1 Document the Heatmap view, the 10 m / 30 s / 300 m / 100 m constants, the virtual-ride rule and the basemap privacy trade-off in README.md, and the new modules, the `activity_tracks` table and the `button_group` testing note in CLAUDE.md. Verify that every constant and command named in the docs exists in the code

## 6. Integration check

- [x] 6.1 On the owner's real database run a scan (the backfill) and check the numbers against the design: about 585 routes with points, 30 virtual rides with none, about 93,000 vertices in total, the routes payload under 5 MB and the Heatmap query and render ready within 3 seconds for the full history; the owner looks at the map and confirms the routes and the density view look right
