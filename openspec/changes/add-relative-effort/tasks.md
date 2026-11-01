# Tasks

Implemented on branch `feature/relative-effort`; the boxes record work already done and verified.

## 1. Relative effort metric

- [x] 1.1 Replace the Edwards TRIMP with a zone-weighted relative effort in `myfitty/metrics/effort.py`, with weights and default zone fractions in `metrics/constants.py`; verify unit tests for per-zone weights, edge values going to the higher zone, time and intensity scaling, JSON string keys, missing inputs and edges derived from max HR
- [x] 1.2 Calibrate the weights against Strava's Relative Effort on the owner's export (monotone fit, then rescale) and record the numbers in design.md; verify the end-to-end comparison on a rescored import: median ratio 1.02 and correlation 0.945
- [x] 1.3 Make `score_activity` use configured zone edges, else edges from max HR (recording `max_hr_used` only in that case); verify a test covering configured edges, derived edges and neither

## 2. Configuration and storage

- [x] 2.1 Read and validate `[relative_effort] zone_edges` in `myfitty/config.py` (four positive ascending values); verify tests for valid, optional, wrong count, not ascending, non-positive and non-numeric edges
- [x] 2.2 Rename `activities.trimp` to `relative_effort` with a guarded migration in `db.connect()`, and have `rescore` and the importer use the configured edges; verify a test that an old column is renamed with its values kept, and a test that rescoring after a zone change recomputes the score
- [x] 2.3 Document `[relative_effort]` in `myfitty.example.toml`, and the score, its calibration and `myfitty rescore` in README.md and CLAUDE.md; verify the documented commands run and the example file loads

## 3. Weekly relative effort chart

- [x] 3.1 Add `queries.weekly_effort` (sum per ISO week, nulls as zero, zero-filled weeks, sport and date filters); verify tests for weekly sums, sport filter, zero weeks and an empty database
- [x] 3.2 Add the weekly relative effort bar chart to the page and use the renamed column in the activity table; verify an `AppTest` that the chart renders and changes with the sport selector

## 4. Import robustness

- [x] 4.1 Reduce array-valued record fields to their latest sample in the parser and add a fixture with array speed and altitude to the test generator; verify a parser test on that fixture and that the previously failing real file now imports
- [x] 4.2 Add `retry_failed` to the scan and `myfitty ingest --retry-failed`; verify importer tests that unchanged failures are skipped unless asked, imported files are not re-read, and the CLI flag works, then run it on the owner's database (3 failed files resolved)

## 5. Integration check

- [x] 5.1 Run the full suite and validate the specs; verify 149 tests pass, `openspec validate add-relative-effort --strict` is clean, and the owner's database is rescored with no import failures

## Workflow follow-up

- Archive this change after the branch is merged (`/opsx:archive`), which updates `openspec/specs/training-load`, `fitness-chart` and `fit-ingest`.
