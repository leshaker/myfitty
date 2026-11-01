# Design

## Context

Greenfield repo; nothing exists yet besides OpenSpec config. Single user, runs locally. See proposal.md for scope and the assumptions made about power, running scoring, combined vs per-sport fitness, and the database. Later changes (Garmin API, Wahoo/Dropbox, heatmaps) will add more sources writing FIT files into the same folder, and GPS tracks to the same database, so ingest must not depend on file origin.

## Goals / Non-Goals

**Goals:**
- A pure, unit-testable metrics layer (no I/O) so TSS/relative effort/PMC can be verified against hand-computed values.
- Idempotent ingest: re-running over the same folder any number of times gives the same database.
- Store enough per-activity data to rescore without re-parsing FIT files: summary metrics (NP, per-bpm time histogram) in the database for fast rescoring, and raw 1 Hz samples in Parquet for anything else.

**Non-Goals:**
- Downsampling GPS tracks, aggregating or rendering them (heatmap change). Samples are stored in Phase 1, but nothing reads the GPS yet.
- Multi-user, auth, or running outside localhost.
- Replicating Strava's exact Relative Effort numbers; this is a comparable zone-weighted score.

## Decisions

**Layout.** Python package `myfitty/` with `ingest/`, `metrics/`, `db.py`, `queries.py` (functions returning DataFrames for PMC, weekly load, activities, sports) and a Streamlit `app.py`. `metrics/`, `queries.py` and `ingest/` import nothing from Streamlit, so the UI can be swapped later. Run with `streamlit run myfitty/app.py`; a Dockerfile can come later.

**FIT parsing: `fitdecode`.** Read `session` for sport/sub_sport/start_time/totals, `device_info` for serial number, and `record` messages for HR and power. Alternative `fitparse` is less maintained.

**Storage: DuckDB for mutable tables, Parquet for bulk samples.** DuckDB file holds `activities` (with a UNIQUE key on start time + serial), `threshold_entries(metric, effective_from, value)` and `ingest_failures`, via plain SQL, no ORM. These need updates (rescoring), upserts and uniqueness, which Parquet files can't do in place. Per-activity samples go to one Parquet file each under `samples/sport=<sport>/year=<yyyy>/<start>_<serial-or-hash>.parquet`, a name derived from the dedupe key and recorded in `activities.sample_path`, so a re-import or crash recovery overwrites the same file, with columns `t` (UTC seconds), `hr`, `power`, `speed`, `lat`, `lon`, `altitude`, resampled to 1 Hz. DuckDB reads them as one dataset with `read_parquet('samples/**/*.parquet', hive_partitioning=true)`. Alternatives: SQLite (no good Parquet story), Parquet-only (no in-place updates). DuckDB allows one read-write process at a time, and Streamlit reruns the script on every interaction, so `db.py` opens a short-lived connection per operation (retrying briefly on lock contention) and never holds one open. This also lets a CLI import (`python -m myfitty.ingest`, e.g. from cron) run while the app is idle. The Parquet file is written to a temp name then renamed, and only then is the `activities` row committed; a crash can leave an orphan Parquet file, which the next scan of that source file overwrites, but never an activity without samples.

**Dedup key.** `UNIQUE(start_time_utc, device_serial)`; when the serial is missing, serial is replaced by `sha256(file)` so identical files still dedupe. The first file seen wins.

**Summary stored at ingest.** `normalized_power` (30 s rolling mean of power, 4th-power mean, 4th root; records are resampled to 1 Hz first and gaps count as zero power), `avg_hr`, `max_hr`, `avg_power`, `moving_seconds`, and `hr_histogram` (JSON: bpm → seconds). Rescoring after a threshold change uses these only. NP for activities under 30 s of power data is null.

**Scores are computed from stored summary, stored in `activities`** (`tss`, `tss_method`, `relative_effort`, `ftp_used`, `thr_hr_used`, `max_hr_used`, `unscored_reason`). Storing them makes threshold history stable (the spec requirement) and makes charts a cheap sum; a rescore function updates the affected rows when a threshold entry is edited.

**Running is HR-only.** `score_activity` takes the sport; sports in `HR_ONLY_SPORTS` (`running`) have power ignored, so they score from hrTSS or are unscored (`no_data` without HR, `no_threshold` without threshold HR). Cycling keeps power > HR. The set lives in `metrics/constants.py` next to the other tunables. Alternatives: a setting in the config file (deferred until a second sport needs it), or scoring runs by a separate running threshold power (deferred with rTSS).

**Rescoring on demand.** Scores are stored, so changing a rule leaves old rows stale. `myfitty rescore` re-runs the scorer over all activities from the stored summary (no FIT parsing) and updates only rows whose score changed. Threshold edits still rescore just their affected range.

**Config file.** Optional `myfitty.toml` (or `MYFITTY_CONFIG`) parsed with `tomllib`. It sets `fit_dir`, `db_path`, `samples_dir` (environment variables win, relative paths are relative to the file) and lists `[[thresholds]]` entries. At startup, in the app once per session and in `myfitty ingest`, entries whose (metric, date) are not stored are inserted through the normal save-and-rescore path; stored entries are never overwritten or deleted, so UI edits win. Invalid files raise a `ConfigError` shown to the user. The personal file is git-ignored; `myfitty.example.toml` documents the format. Alternative considered: make the file authoritative (sync both ways), rejected because it would silently discard values edited in the UI.

**Console entry point.** `myfitty app` (runs Streamlit on `app.py`, extra options pass through), `myfitty ingest`, `myfitty rescore`.

**hrTSS.** Zones as % of threshold HR: Z1 <81%, Z2 81–89%, Z3 90–93%, Z4 94–99%, Z5 ≥100%, contributing 20/40/60/80/100 TSS per hour (the TrainingPeaks-style approximation). Chosen as a simple, documented table; the spec only requires roughly 100 TSS for an hour at threshold. The table lives in one constants module so it can be tuned.

**Relative effort.** Zone-weighted minutes: `sum(minutes in zone × weight)` over five HR zones, with weights `(0.3, 0.3, 2.1, 2.1, 2.4)` per minute (`metrics/constants.py`). Zone edges are four bpm values from `[relative_effort] zone_edges` in the config file, or by default fractions of the applicable max HR (63/80/84/90%). The score is stored in `activities.relative_effort` (renamed from `trimp`; connecting to an older database renames the column, and `myfitty rescore` recomputes the values) and charted per ISO week. Calibration: the weights are a monotone least-squares fit of per-zone minutes (zones 114/146/153/163 bpm) to the Strava Relative Effort in the owner's export, on about 390 activities. Result against Strava: log-correlation 0.95, median ratio 1.02, per-activity error about 19% for rides and runs; walks and hikes come out roughly 40% low, which is acceptable. Alternatives measured on the same data: Edwards TRIMP (the previous formula; log-correlation 0.87, about 4-5x too high for rides and runs, p90/p10 ratio spread 5.2x), Banister TRIMP (0.91, 3.9x), smooth power/exponential curves (0.91, 3.3x), and five unconstrained zone weights (0.95 but Z3 above Z4, so not monotone). Strava's own algorithm is proprietary and its zones changed over the years, so an exact match is not a goal.

**PMC.** Daily TSS series per sport filter (a SQL `GROUP BY` over `activities`), then `CTL_t = CTL_{t-1} + (TSS_t − CTL_{t-1}) / 42`, same for ATL with 7. TSB is same-day CTL − ATL, as the brief defines it (note: TrainingPeaks uses the previous day's values; not copied here). Always computed from the first activity so windowing only slices the result. Days use the activity's local start date; the local timezone is the machine's, since FIT stores UTC with an optional offset.

**Query layer.** `queries.py` exposes `pmc(sport, start, end)`, `weekly(sport)`, `activities(sport, start, end)` and `sports()`, plus threshold CRUD in `db.py`. The Streamlit page only calls these. There is no REST API in this phase; if a later change needs one (e.g. Garmin sync as a separate service), it can wrap the same functions.

**Concurrency.** Streamlit runs each browser session in its own thread, and a reload starts a new session, so two imports (or an import and a threshold edit) can overlap. DuckDB aborts one of two conflicting transactions, which crashed the page and could record a good file as failed. Writers (`scan`, threshold save/remove/seed, `rescore`) take one re-entrant `db.WRITE_LOCK`, so a second import waits and then finds the files already imported; schema setup has its own lock so opening a connection never waits for an import. A unique-key violation on the activity insert (another process won the race) is reported as a duplicate. Across processes (CLI vs app) DuckDB's file lock plus the connect retry already serialize. Alternative: a lock file, rejected as unnecessary for one process.

**Retrying failures.** Unchanged failed files are skipped on later scans, so a parser fix does not help them by itself. `myfitty ingest --retry-failed` re-reads every failed file once (imported files are never re-read).

**Ingest trigger.** No watcher in this phase. The app scans the FIT folder once per browser session (guarded with `st.session_state`) and on an "Import now" button; `python -m myfitty.ingest` does the same from the command line. A `source_files(path, size, mtime, status)` table lets a scan skip unchanged files cheaply, retry failed files only when their size or mtime changed, and avoid reading files modified in the last 2 s (half-written copies). The folder path comes from `MYFITTY_FIT_DIR` (default `./fit`), the DB from `MYFITTY_DB`.

**Frontend: Streamlit + Altair.** One page: sidebar with sport, date range and an "Import now" button; main area with the PMC chart (CTL and ATL as lines, TSB as an area or line on a shared date axis), weekly load bars, an activity table, and a thresholds form (`st.form`) with the threshold history. Altair's 5,000-row limit is disabled (`alt.data_transformers.disable_max_rows()`). Queries are cached with `st.cache_data` and cleared after an import or threshold change. Chosen over FastAPI + ECharts for speed of development; the cost is that no server-side work runs without an open session, hence the on-open ingest.

## Risks / Trade-offs

- [Different NP/TSS than Strava or Garmin because of resampling and pause handling] → Define it once in the metrics module, unit-test it, and don't promise parity.
- [HR-based TSS for running is coarse] → Isolated constants table; pace rTSS is a later change.
- [Streamlit reruns the whole script on each interaction, so slow queries would make the UI sluggish] → Cache query results; data volume is small.
- [New files are not imported until the app is opened or a CLI import runs] → Accepted for Phase 1; a daemon comes with the Garmin sync change.
- [Same-day CTL−ATL differs from TrainingPeaks] → Documented; one-line change if preferred.
- [Dedup misses the same activity from two devices, which have different serials] → Accepted; a later change can add fuzzy matching on start time ± a few seconds and duration.
- [Parquet sample files grow with activity count (roughly 100-300 KB per hour with GPS)] → Fine for personal use; compression is on by default.
- [Timezone: activities near midnight can land on a different day if the machine's timezone changes] → Accepted for a single-user local app.
- [Threshold history entered late means everything is unscored until it exists] → Unscored reasons are shown, and adding the first threshold triggers rescoring.
