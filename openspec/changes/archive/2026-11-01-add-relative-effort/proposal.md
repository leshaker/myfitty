# Proposal

## Why

The phase 1 app computes a relative-effort score with the Edwards TRIMP formula. Checked against Strava's own Relative Effort for about 390 of the owner's rides and runs, it runs 4–5× too high and its ratio to Strava varies 5× from activity to activity, because easy long efforts are weighted too heavily. Strava names Banister's TRIMP as its model and weights high heart rates much more steeply. A score close to Strava's is the point of the app, and it is only shown in a table today. Importing the full Strava export (about 645 FIT files) also exposed two import problems: one file format variant fails to parse, and a file that failed once is never retried, even after the parser is fixed.

## What Changes

- Replace the Edwards TRIMP with a zone-weighted **relative effort**: minutes in each of five heart-rate zones times a per-minute weight (0.3 / 0.3 / 2.1 / 2.1 / 2.4). The weights are calibrated to Strava's numbers and kept non-decreasing. Result against Strava on the same activities: median ratio 1.02, correlation 0.95, about 19% error per ride or run (walks and hikes come out about 40% low).
- Zone edges (upper bounds of zones 1–4, in bpm) come from an optional `[relative_effort] zone_edges` setting in `myfitty.toml`, and default to fixed fractions of max HR when not set.
- **BREAKING**: the stored column `activities.trimp` becomes `relative_effort` and its values change. Existing databases are migrated on open; `myfitty rescore` recomputes the values.
- Add a weekly relative effort bar chart on the page, next to weekly TSS, following the same sport and date filters.
- Read FIT records whose fields hold several samples per record (arrays, as some Garmin devices write); the latest sample is used.
- Add `myfitty ingest --retry-failed` to re-read files that failed before and are unchanged.

Out of scope: a relative-effort fitness/fatigue curve, calibrating walks and hikes, and zone edges that change over time.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `training-load`: relative effort becomes a zone-weighted score with configurable zone edges (replacing the TRIMP requirement), plus validation of the configured edges.
- `fitness-chart`: adds weekly relative effort, and the page shows it as a second weekly chart.
- `fit-ingest`: imports activities with array-valued record fields, and failed files can be retried on request.

## Impact

- Code: `myfitty/metrics/` (new `effort.py` replacing `trimp.py`, constants, scoring), `config.py` (zone edges), `db.py` (column rename migration), `rescore.py`, `ingest/` (parser, importer, CLI flag), `queries.py` (weekly relative effort), `app.py` (new chart, renamed column).
- Data: existing `trimp` values are replaced after `myfitty rescore`; no FIT files are re-read.
- Config: new optional `[relative_effort]` section in `myfitty.toml` and `myfitty.example.toml`.
- Docs: README metric definitions and `CLAUDE.md`.
- Implementation already exists on branch `feature/relative-effort`; these artifacts describe it.
