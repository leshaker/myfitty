"""Tunable scoring tables."""

# hrTSS: zones as a fraction of threshold HR (exclusive upper bound) -> TSS per hour in that zone.
# A TrainingPeaks-style approximation: an hour at or above threshold scores about 100.
HR_TSS_ZONES = (
    (0.81, 20.0),            # Z1: below 81%
    (0.90, 40.0),            # Z2: 81-89%
    (0.94, 60.0),            # Z3: 90-93%
    (1.00, 80.0),            # Z4: 94-99%
    (float("inf"), 100.0),   # Z5: at or above threshold
)

# Relative effort (a HR-based load similar to Strava's): minutes in each of five heart-rate zones times a
# per-minute weight. Weights are calibrated against the owner's Strava Relative Effort history (monotone
# least-squares on ~390 activities, zones 114/146/153/163 bpm; log-correlation 0.95), so values land near
# Strava's. Tune here, then run `myfitty rescore`.
RELATIVE_EFFORT_WEIGHTS = (0.3, 0.3, 2.1, 2.1, 2.4)       # Z1..Z5, per minute
# Zone edges (upper bound of Z1..Z4) as fractions of max HR, used when no explicit edges are configured.
DEFAULT_ZONE_FRACTIONS = (0.63, 0.80, 0.84, 0.90)

# Sports scored from heart rate only, even when the file has power data: running power is not
# comparable with a cycling FTP, so power TSS would be wrong. FIT `session.sport` names.
HR_ONLY_SPORTS = frozenset({"running"})

NP_WINDOW_SECONDS = 30
CTL_DAYS = 42
ATL_DAYS = 7
