# Design

## Context

Phase 1 stores a per-activity score `trimp` (Edwards formula: weights 1–5 on fixed 50–100% bands of max HR) and shows it only in the activity table. The owner's Strava export gives Strava's own Relative Effort for about 390 rides and runs, which makes it possible to measure how close any formula is. See proposal.md for the motivation. The importer reads the owner's whole export (about 645 FIT files), which also surfaced the parser and retry gaps below.

## Goals / Non-Goals

**Goals:**
- A relative-effort score close to Strava's in size and ranking, from the stored heart-rate histogram only (no FIT re-reading).
- Zones the owner can set to match their lab or Strava zones.
- A safe upgrade of an existing database.

**Non-Goals:**
- Reproducing Strava's algorithm exactly (it is proprietary and its zones changed over the years).
- Calibrating walks and hikes, which come out about 40% low.
- Zone edges that vary by date.
- A fitness/fatigue curve built on relative effort.

## Decisions

**Formula: zone-weighted minutes.** `sum(minutes in zone × weight)` over five zones, weights `(0.3, 0.3, 2.1, 2.1, 2.4)` per minute, in `metrics/constants.py`. It lives in `metrics/effort.py` (pure, replacing `trimp.py`). Measured against Strava's Relative Effort on the same ~390 activities:

| Model | Log-correlation | Ratio spread (p90/p10) |
|---|---|---|
| Edwards TRIMP (previous) | 0.87 | 5.2x |
| Banister TRIMP (resting HR 45–60) | 0.91 | 3.9x |
| Smooth power / exponential curves | 0.91 | 3.3x |
| Five unconstrained zone weights | 0.95 | 2.3x (but zone 3 above zone 4) |
| Monotone zone weights (chosen, ×1.1, rounded) | 0.95 | 2.3x |

Monotone least squares (pool-adjacent-violators on relative error) gives the chosen weights without the non-monotone artefact, then a ×1.1 rescale puts the median ratio at 1.0. End to end after the change: median ratio 1.02, correlation 0.945, about 19% mean error for rides and runs, and per-sport totals within 5% for cycling (18,796 against 18,830) and running (3,958 against 3,795). Banister was rejected because it needs a resting HR and still matches worse.

**Zones: four bpm edges.** Zone n is `bisect_right(edges, bpm)`, so a value on an edge goes to the higher zone. Edges come from `[relative_effort] zone_edges` in the config file (validated: four values, positive, strictly ascending, else `ConfigError` shown at startup) and otherwise from `DEFAULT_ZONE_FRACTIONS = (0.63, 0.80, 0.84, 0.90)` of the max HR in effect on the activity's date (`max_hr_used` is recorded only in that case). Explicit edges are one global setting, not dated: the owner's Strava zones changed over time, but dated zones are not needed to get within 20% per activity.

**Storage and upgrade.** The column is renamed `trimp` → `relative_effort` (`ALTER TABLE ... RENAME COLUMN` in `db.connect()`, guarded by a column check, under the existing schema lock). Old values are kept until `myfitty rescore` recomputes them from the stored histogram. Alternative: keep the old column name and change its meaning, rejected because the name would mislead.

**Rescoring.** `rescore` and the importer pass the configured edges into `score_activity`; when called without them, `rescore` reads the config itself and ignores an invalid config rather than failing a threshold edit.

**Weekly chart.** `queries.weekly_effort` sums `relative_effort` per local date (null counts zero), zero-fills to today with the same daily routine as the load series, windows it to the selected range, and sums per ISO week. The page draws it as a second weekly bar chart in a distinct colour with one band per week.

**Array-valued fields.** Some Garmin devices write several samples per record (for example `enhanced_speed` as three values); `fitdecode` returns a tuple, which made the 1 Hz resample fail for one real file. The parser's field reader now reduces any tuple or list to its last non-null element. The test generator can write array fields so the case has a fixture.

**Retrying failures.** Unchanged failed files are skipped by design (re-parsing a corrupt file on every scan is wasteful), so a parser fix did not help them. `scan(retry_failed=True)` ignores `failed` rows when deciding what is unchanged; `myfitty ingest --retry-failed` exposes it. Files that imported or were duplicates are never re-read.

## Risks / Trade-offs

- [Weights are fitted to one person's Strava history and zones] → They are constants in one place with the calibration noted; re-fitting is a small script, and `myfitty rescore` applies a change.
- [Walks and hikes score about 40% below Strava] → Accepted; they carry little load and a separate fit would overfit 57 activities.
- [Existing `trimp` values stay stale until rescored] → The README and `CLAUDE.md` say to run `myfitty rescore`, and the owner's database has been rescored.
- [Global zone edges mis-score years when the owner's zones were different] → Accepted for now; dated zones are a later change if it matters.
- [A config typo in the zone edges stops the app] → Intentional: the error names the setting and what is expected.
