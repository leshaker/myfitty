# Proposal

## Why

Strava's heatmaps show where you actually ride and run, grouped by sport, and they are part of what the app is meant to replace. The GPS is already stored: every imported activity keeps its 1 Hz samples, including latitude and longitude, in Parquet. Nothing reads it yet. On the owner's real data (about 585 outdoor activities, 2.8 million GPS seconds, 17,400 km) the raw points are far too many to draw on a map page: five-second points would be about 15 MB of JSON per filter change. A simplified track per activity, built once, makes a map fast.

Two properties of real data matter too. Thirty rides are virtual (Zwift-style) and carry GPS in the South Pacific (about latitude −22, longitude 167); drawn on a map they would wreck the view. And GPS drops out: 585 activities contain 2,577 separate stretches once pauses and jumps are split, and a line drawn across a dropout is a lie.

## What Changes

- Build a simplified route for every activity with GPS when it is imported: split at GPS gaps (no fix for 30 s, or a jump over 300 m), then thin each stretch with Douglas–Peucker at 10 m. On real data this keeps 3.3% of the points (about 93,000 in total, 2.4 MB) and takes about 10 ms per activity.
- Store the routes in the database, and fill them in for activities imported earlier on the next scan, the same way maximum power was backfilled. Routes of virtual rides are never stored.
- Add a **Heatmap** tab to the page with two views over the same sport and date filters:
  - **Routes**: every route drawn as a thin, translucent line so overlapping routes build up into a heatmap, coloured by sport when all sports are shown.
  - **Density**: a smoothed heat layer, sampled evenly every 100 m along the routes so long straight stretches count as much as winding ones.
- Fit the map to the filtered routes, let the basemap be switched off, and show an empty state when nothing has GPS.

Out of scope: hiding a radius around home (privacy zones), a route detail map for a single activity, heatmaps from GPX/TCX files, and offline map tiles.

## Capabilities

### New Capabilities
- `route-heatmap`: the Heatmap view of routes and density, its filters, exclusions and empty state.

### Modified Capabilities
- `fit-ingest`: stores a simplified route for each activity with GPS, skips virtual rides, and fills routes in for activities imported before this change.

## Impact

- Code: new `myfitty/ingest/tracks.py` (gap splitting, simplification), a new table and backfill in `db.py` and `ingest/importer.py`, route and density queries in `queries.py`, and a Heatmap tab in `app.py`.
- Data: a new `activity_tracks` table, about 2.4 MB for the owner's history. Existing activities get routes on the next scan by reading their Parquet samples, with no FIT files re-read.
- Dependencies: none. `pydeck` (deck.gl for Python) already ships with Streamlit.
- Privacy: everything stays local. The one external request is the basemap tiles, which tell the tile provider which area is on screen; the basemap can be switched off.
