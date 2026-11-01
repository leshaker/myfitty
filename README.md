# myfitty

Local, single-user training-status app (a Strava Premium replacement). It imports FIT files from a
folder and shows fitness, fatigue, form and weekly load. No cloud, no auth. Planning artifacts live
in `openspec/`.

## Setup and run

```bash
uv venv .venv && uv pip install -e '.[dev]'     # or: python -m venv .venv && .venv/bin/pip install -e '.[dev]'
export MYFITTY_FIT_DIR=~/Dropbox/Apps/WahooFitness    # any folder of .fit files (read-only)
.venv/bin/streamlit run myfitty/app.py
```

1. Open the page and expand **Thresholds** in the sidebar. Add your FTP, threshold HR and max HR
   with the date they apply from. Without them activities are listed but unscored.
2. The app scans the FIT folder when you open it and whenever you press **Import now**. Files
   already imported (same size and modification time) are skipped; files modified in the last
   2 seconds are left for the next scan.
3. Pick a sport and date range in the sidebar. CTL and ATL always use your full history, so a
   shorter range never changes the values.

Import from the command line (for example from cron) with `python -m myfitty.ingest`. The app and the CLI
can both be used, but not at the exact same moment (DuckDB allows one writer; each waits a few
seconds for the other).

Try it with the bundled fixtures: `MYFITTY_FIT_DIR=tests/fixtures streamlit run myfitty/app.py`
(their dates are in March 2026, so widen the date range, which defaults to the last 180 days).

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MYFITTY_FIT_DIR` | `./fit` | Folder scanned (recursively) for `.fit` files; never modified |
| `MYFITTY_DB` | `./data/myfitty.duckdb` | DuckDB file: activities, thresholds, scores |
| `MYFITTY_SAMPLES_DIR` | `./data/samples` | Parquet files with each activity's 1 Hz samples |

## What gets stored

- **DuckDB**: one row per activity with summary metrics (duration, distance, HR/power averages,
  normalized power, seconds per heart rate) and its scores; the dated threshold history; and which
  source files have been seen.
- **Parquet**: each activity's samples resampled to 1 per second (`t`, `hr`, `power`, `speed`, `lat`, `lon`,
  `altitude`) under `samples/sport=<sport>/year=<yyyy>/`. Read them all with
  `read_parquet('data/samples/**/*.parquet', hive_partitioning=true)` in DuckDB.
- Activities are deduplicated on start time + device serial number (or, without a serial, a hash of the
  file), so the same ride arriving from two folders or under another filename is imported once.

## Metric definitions

Thresholds are looked up by the activity's local start date: the latest entry on or before it (the
earliest entry if none is that old). Adding a newer entry never changes older activities' scores.
Editing or deleting an entry rescores only the activities it applies to.

- **NP** (normalized power): 1 Hz power (gaps count as 0), 30 s rolling mean, mean of the 4th powers, 4th root.
  Not computed for under 30 s of data.
- **TSS (power)**: `hours × (NP / FTP)² × 100`, using moving time.
- **hrTSS** (when there is no power or no FTP): seconds at each heart rate, grouped by % of threshold HR,
  each zone scoring a fixed TSS per hour:

  | % of threshold HR | <81 | 81–89 | 90–93 | 94–99 | ≥100 |
  |---|---|---|---|---|---|
  | TSS per hour | 20 | 40 | 60 | 80 | 100 |

  The table is in `myfitty/metrics/constants.py`.
- **Relative effort** (Edwards TRIMP): minutes in each zone of % max HR times the weight:
  50–60% ×1, 60–70% ×2, 70–80% ×3, 80–90% ×4, 90–100% ×5; below 50% counts 0.
- **CTL / ATL**: exponentially weighted averages of daily TSS with 42- and 7-day constants,
  `x += (tss - x) / N`, starting from 0. Days without activity count as 0 and the series runs to today.
- **TSB** (form) = CTL − ATL on the same day.
- **Weekly load**: total TSS per ISO week (Monday start).
- Power TSS is used when both power and FTP exist, otherwise hrTSS, otherwise the activity is unscored
  (`no_data` or `no_threshold`) and counts as 0 load.

## Tests

`.venv/bin/pytest`. FIT fixtures in `tests/fixtures/` come from `python -m tests.fitgen`.
