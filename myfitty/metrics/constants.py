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

# Edwards TRIMP: zone floor as a fraction of max HR -> weight. Below the first floor counts as zero.
TRIMP_ZONES = ((0.5, 1), (0.6, 2), (0.7, 3), (0.8, 4), (0.9, 5))

# Sports scored from heart rate only, even when the file has power data: running power is not
# comparable with a cycling FTP, so power TSS would be wrong. FIT `session.sport` names.
HR_ONLY_SPORTS = frozenset({"running"})

NP_WINDOW_SECONDS = 30
CTL_DAYS = 42
ATL_DAYS = 7
