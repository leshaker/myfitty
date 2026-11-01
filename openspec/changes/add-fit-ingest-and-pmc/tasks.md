# Tasks

## 1. Project scaffolding

- [x] 1.1 Create the Python package layout (`myfitty/{ingest,metrics}`, `db.py`, `queries.py`, `app.py`, `tests/`), `pyproject.toml` with streamlit, altair, fitdecode, duckdb, pyarrow, numpy, pandas, pytest; verify `pip install -e .` and `pytest` (zero tests) both succeed
- [x] 1.2 Add config loading for `MYFITTY_FIT_DIR`, `MYFITTY_DB` and `MYFITTY_SAMPLES_DIR` and a README with the run command; verify `streamlit run myfitty/app.py` starts and shows an empty-state page (checked with Streamlit's `AppTest`)

## 2. Database and thresholds

- [x] 2.1 Create the DuckDB schema (`activities` with UNIQUE start time + serial, `threshold_entries`, `ingest_failures`) applied at startup, via short-lived connections with lock retry, plus a `source_files` table; verify tests that the schema is created idempotently, survives reopening the file, and that a second connection succeeds after the first closes
- [x] 2.2 Implement threshold storage and by-date lookup (latest on or before date, else earliest, else none) and validation; verify tests for the thresholds scenarios (between entries, before first, none, same-date replace, invalid values)
- [x] 2.3 Add threshold create/replace/delete functions in `db.py` with validation errors; verify tests for add, replace, delete and rejected invalid input

## 3. Metrics (pure functions)

- [x] 3.1 Implement normalized power, power TSS and IF in `metrics/tss.py`; verify tests for 1 h at FTP → 100, 2 h at 75% → 112.5, and short or missing power → null
- [x] 3.2 Implement hrTSS from the per-bpm histogram with the zone table in a constants module; verify a test that 1 h at threshold HR is within 10% of 100
- [x] 3.3 Implement TRIMP in `metrics/trimp.py`; verify 30 min at 75% max HR → 90 and no HR → null
- [x] 3.4 Implement the scoring selector (power > HR > unscored with reason) returning method and thresholds used; verify tests for each precedence case
- [x] 3.5 Implement the PMC calculation in `metrics/pmc.py` (daily TSS, CTL 42, ATL 7, TSB, zero-fill to today) and weekly ISO-week totals; verify tests for the single-day, rest-decay, multi-activity, zero-fill, windowing and weekly scenarios

## 4. FIT ingest

- [x] 4.1 Add small FIT fixtures (power+HR ride, HR-only run, no-sensor file, non-activity file, corrupt file) under `tests/fixtures/` and a helper to generate them; verify the fixtures load in a test
- [x] 4.2 Implement the FIT parser extracting sport/sub-sport, start time, serial, durations, distance, HR/power summary, NP and HR histogram; verify parser tests for each fixture, including sport `unknown`
- [x] 4.3 Resample records to 1 Hz and write each activity's samples to a Parquet file (temp file then rename), partitioned by sport and year; verify a test that the file reads back through DuckDB `read_parquet` with the expected columns and row count, and that lat/lon are null for the indoor fixture
- [x] 4.4 Implement the folder importer with dedup (serial, or file hash fallback), per-file error capture and a result report, then score each new activity; verify tests for duplicate file, renamed duplicate, corrupt file in a batch, non-activity skip, retry after fix, and source folder unchanged
- [x] 4.5 Implement rescoring of affected activities on threshold add/edit/delete and when the first threshold appears; verify tests that earlier activities keep their score and a corrected entry rescores only its range
- [x] 4.6 Add scan-on-demand using `source_files` (skip unchanged files, retry changed failures, skip files modified within 2 s) and a `python -m myfitty.ingest` CLI; verify tests that an unchanged file is not re-parsed, a replaced failed file is imported, and a recently modified file is deferred

## 5. Query layer and Streamlit page

- [x] 5.1 Implement `queries.py` (`pmc`, `weekly`, `activities`, `sports`) with sport and date filters returning DataFrames; verify tests for sport filter, combined view, and that a windowed CTL equals the full-history value
- [x] 5.2 Build `app.py`: sidebar (sport, date range, Import now with once-per-session scan on open), PMC chart, weekly load bars, activity table with score method and TRIMP, empty state; cache queries and clear on import; verify with `streamlit.testing.v1.AppTest` against a seeded database that both charts render, sport changes update them, and the empty state appears with no data
- [x] 5.3 Add the thresholds form and history table to the page; verify with `AppTest` that submitting a new FTP stores it, rescored activities change, and an invalid value shows an error
- [x] 5.4 Document setup, configuration, running the app and the CLI import, threshold entry and the metric definitions (NP, TSS, hrTSS table, TRIMP, CTL/ATL/TSB) in the README; verify that following it from a clean checkout imports the fixtures and shows the chart

## 6. Integration check

- [ ] 6.1 Import a real folder of personal Wahoo and Garmin FIT files, set thresholds, and verify no failures other than expected non-activity files and that the chart looks plausible against Strava's fitness curve
