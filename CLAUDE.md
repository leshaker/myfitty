# myfitty

Local, single-user training-status app (a Strava Premium replacement): imports FIT files from a folder,
scores activities (TSS, relative effort) and shows fitness/fatigue/form. Python, Streamlit + Altair,
DuckDB, Parquet. This is a hobby project: there are **no Jira tickets**, so commit messages and branch
names carry no ticket ID (plain descriptive messages; branches like `feature/<topic>`).

## Commands

```bash
uv venv .venv && uv pip install -e '.[dev]'    # setup
.venv/bin/pytest                               # full test suite (must pass before committing)
uv run myfitty app                             # start the UI (extra args go to `streamlit run`)
uv run myfitty ingest                          # import the FIT folder (--retry-failed re-reads earlier failures)
uv run myfitty rescore                         # recompute all stored scores after a scoring-rule change
openspec validate add-fit-ingest-and-pmc --strict
python -m tests.fitgen                         # regenerate tests/fixtures/*.fit (a test fails if they drift)
```

## Spec-driven workflow

Behavior is specified with OpenSpec in `openspec/changes/<change>/` (proposal, delta specs per capability,
design, tasks). When code changes behavior, update the matching spec scenario, `design.md` and `tasks.md`
in the same change, and keep `openspec validate --strict` clean. Tasks are checkboxes in `tasks.md`.
The current change is `add-fit-ingest-and-pmc`; task 6.1 (import the real FIT folder) needs the owner's own files.

## Architecture rules

- `myfitty/metrics/` is pure (no I/O, no Streamlit). `ingest/`, `queries.py`, `rescore.py` and `db.py` must not
  import Streamlit; only `app.py` does.
- DuckDB allows one read-write process. `db.connect()` opens a short-lived connection per operation (retrying
  on the file lock); never hold one open. Writers (`scan`, threshold save/remove/seed, `rescore`) take
  `db.WRITE_LOCK`, because Streamlit runs each browser session in its own thread.
- Scores are stored in `activities`, computed from stored summaries (NP, per-bpm histogram), not from FIT files.
  After changing a scoring rule, run `myfitty rescore`. Thresholds are effective-dated; adding one never
  rescored earlier activities.
- Relative effort is zone-weighted minutes (`metrics/constants.py` weights, calibrated to Strava's Relative Effort);
  zone edges come from `[relative_effort] zone_edges` in `myfitty.toml`, else from max HR. The column is
  `activities.relative_effort` (was `trimp`; renamed by a migration in `db.connect()`).
- **Running is scored by heart rate only** (`HR_ONLY_SPORTS` in `metrics/constants.py`), never by power.
- Per-activity 1 Hz samples go to Parquet under `samples/sport=…/year=…/`; the file name derives from the dedupe
  key, so a re-import overwrites the same file. Schema changes need an `ALTER … IF NOT EXISTS` migration in
  `db.connect()` because the user's database already exists.
- `start_time` is stored as naive UTC; `local_date` is the machine-local date used for daily load.

## Testing notes

- `tests/conftest.py` runs every test in an empty temp dir so a real `./myfitty.toml` is never read.
- Streamlit `AppTest`: charts are `vega_lite_chart` elements (data is an Arrow stream in `proto.datasets`); the
  series toggle is a `button_group`; give buttons a `key=` and look them up by key, because form submit buttons
  also appear in `at.button`.
- Concurrency tests run real threads; keep them passing repeatedly, not just once.

## Public repo: keep personal data out

The GitHub repo is public. Never commit `myfitty.toml` (personal thresholds; git-ignored, use
`myfitty.example.toml`), `data/`, `fit/`, FIT files, or lab reports. Test fixtures are synthetic.

## Git / PRs

Work on a feature branch, not `main`. The `gh` token in this environment cannot create or comment on PRs, so
give the user the compare URL and the PR text instead.
