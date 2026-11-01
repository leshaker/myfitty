# Proposal

## Why

Strava Premium's training-status features (fitness, fatigue, form, relative effort) sit behind a subscription and a cloud account. A single-user, local-first app can compute the same metrics from the FIT files I already have. This change lays the foundation: get activities in from a folder and show the fitness/fatigue/form chart. Garmin sync and heatmaps need that data model first.

## What Changes

- New local Python Streamlit app (Altair charts) with a DuckDB database plus Parquet files for per-activity samples, run with `streamlit run` or in one Docker container. No auth, no cloud.
- Ingest FIT files from a local folder (scanned when the app opens and on an "Import now" button; unchanged files are skipped), parse them, and store one activity per ride/run/etc.
- Deduplicate on start time + device serial, so re-importing the same file or the same activity from two sources is a no-op.
- Store FTP, threshold HR and max HR with effective dates; each activity is scored with the thresholds in effect on its date.
- Compute per-activity load: TSS from power when available, otherwise hrTSS from HR; plus a zone-weighted "relative effort" (like Strava's) and a weekly relative effort chart.
- Compute the performance management chart: CTL (42-day), ATL (7-day), TSB (CTL − ATL), and weekly load.
- An optional `myfitty.toml` read at startup (folders and a threshold history); configured thresholds fill gaps without overwriting what is stored, and the personal file is git-ignored.
- Console commands: `myfitty app`, `myfitty ingest` and `myfitty rescore`.
- A Streamlit page showing the PMC chart and weekly load bars, with sport and date filters and a thresholds form.

Out of scope (later changes): a background folder watcher/sync daemon, Garmin Personal API sync, Wahoo/Dropbox specifics, GPS tracks and heatmaps, pace-based rTSS, the unspecified 4th feature.

Assumptions (answers to the brief's open questions; revisit if wrong):
- Cycling uses power when a file has it and an FTP exists, otherwise HR. This works with or without a power meter.
- Running is always scored by HR, even when the watch records running power, because running power is not comparable with a cycling FTP. Pace-based rTSS is deferred.
- One combined fitness number across sports, with a per-sport filter that recomputes the curves from only that sport's load.
- Streamlit with Altair for the UI (no REST API in this phase). No background watcher: Streamlit only runs code while a browser session is open, so ingest happens on app open and on demand.
- DuckDB for mutable tables (activities, thresholds). Parquet only for bulk columnar data: each activity's 1 Hz samples, which the later heatmaps change will read for GPS.

## Capabilities

### New Capabilities
- `fit-ingest`: importing FIT files from a local folder into stored, deduplicated activities with sport and summary metrics.
- `training-thresholds`: effective-dated FTP, threshold HR and max HR, and which values apply to an activity.
- `training-load`: per-activity TSS (power or HR based) and zone-weighted relative effort.
- `fitness-chart`: daily CTL/ATL/TSB and weekly load, computed by a query layer and displayed in the Streamlit app.

### Modified Capabilities

None (no existing specs).

## Impact

- New code: `ingest/`, `metrics/`, `queries.py`, `app.py` plus a DuckDB schema and Parquet sample storage and a small test suite with sample FIT fixtures.
- New dependencies: Streamlit, Altair, `fitdecode`, duckdb, pyarrow, numpy/pandas.
- New local data: a DuckDB file, a `samples/` Parquet directory, and a configured FIT folder (read-only access to it).
