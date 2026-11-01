from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from myfitty.metrics.pmc import daily_pmc, weekly_load, window
from myfitty.metrics.scoring import score_activity
from myfitty.metrics.effort import default_zone_edges, relative_effort
from myfitty.metrics.tss import hr_tss, normalized_power, power_tss


# --- 3.1 power ---
def test_np_constant_power():
    assert normalized_power([200] * 3600) == pytest.approx(200)


def test_np_exceeds_average_for_variable_power():
    p = ([100] * 60 + [300] * 60) * 30
    assert normalized_power(p) > np.mean(p)


def test_np_short_or_missing():
    assert normalized_power([200] * 29) is None
    assert normalized_power([]) is None
    assert normalized_power([np.nan] * 60) == 0.0  # gaps count as zero


def test_power_tss_hour_at_ftp():
    tss, if_ = power_tss(250, 250, 3600)
    assert tss == pytest.approx(100) and if_ == pytest.approx(1)


def test_power_tss_two_hours_at_75pct():
    tss, _ = power_tss(150, 200, 7200)
    assert tss == pytest.approx(112.5, abs=0.1)


def test_power_tss_missing_inputs():
    assert power_tss(None, 250, 3600) == (None, None)
    assert power_tss(200, None, 3600) == (None, None)


# --- 3.2 hrTSS ---
def test_hr_tss_hour_at_threshold():
    assert hr_tss({165: 3600}, 165) == pytest.approx(100, rel=0.1)


def test_hr_tss_easy_is_low_and_zone_boundaries():
    assert hr_tss({100: 3600}, 165) == pytest.approx(20)
    assert hr_tss({150: 3600}, 165) == pytest.approx(60)  # 90.9% -> Z3
    assert hr_tss({"150": 1800}, 165) == pytest.approx(30)  # JSON keys are strings


def test_hr_tss_missing():
    assert hr_tss({}, 165) is None and hr_tss({150: 60}, None) is None


# --- 3.3 relative effort ---
EDGES = (114, 146, 153, 163)     # Z1 <114 | Z2 <146 | Z3 <153 | Z4 <163 | Z5 >=163


def test_relative_effort_weights_each_zone():
    for bpm, w in ((100, 0.3), (130, 0.3), (150, 2.1), (158, 2.1), (170, 2.4)):
        assert relative_effort({bpm: 600}, EDGES) == pytest.approx(10 * w)   # 10 minutes in one zone


def test_relative_effort_zone_boundaries_belong_to_the_next_zone():
    assert relative_effort({146: 60}, EDGES) == pytest.approx(2.1)           # exactly on the Z2/Z3 edge -> Z3
    assert relative_effort({145: 60}, EDGES) == pytest.approx(0.3)


def test_relative_effort_adds_up_and_grows_with_time_and_intensity():
    mixed = relative_effort({120: 1800, 150: 1200, 170: 600}, EDGES)
    assert mixed == pytest.approx(30 * 0.3 + 20 * 2.1 + 10 * 2.4)
    assert relative_effort({150: 3600}, EDGES) > relative_effort({150: 1800}, EDGES) > 0
    assert relative_effort({170: 1800}, EDGES) > relative_effort({150: 1800}, EDGES)


def test_relative_effort_json_string_keys_and_unordered_edges():
    assert relative_effort({"150": 1800}, (163, 114, 153, 146)) == pytest.approx(30 * 2.1)


def test_relative_effort_missing_inputs():
    assert relative_effort(None, EDGES) is None and relative_effort({}, EDGES) is None
    assert relative_effort({150: 60}, None) is None


def test_default_zone_edges_come_from_max_hr():
    assert default_zone_edges(None) is None
    e = default_zone_edges(200)
    assert e == pytest.approx((126, 160, 168, 180))
    assert relative_effort({150: 600}, e) == pytest.approx(10 * 0.3)         # 75% of max: Z2


# --- 3.4 scoring selector ---
TH = {"ftp": 250, "threshold_hr": 165, "max_hr": 190}


def test_power_wins_when_both():
    r = score_activity({"moving_seconds": 3600, "normalized_power": 250, "hr_histogram": {150: 3600}}, TH)
    assert r["tss"] == pytest.approx(100) and r["tss_method"] == "power"
    assert r["ftp_used"] == 250 and r["thr_hr_used"] is None and r["max_hr_used"] == 190
    assert r["relative_effort"] is not None and r["unscored_reason"] is None


def test_hr_fallback_without_power():
    r = score_activity({"moving_seconds": 3600, "hr_histogram": {165: 3600}}, TH)
    assert r["tss_method"] == "hr" and r["thr_hr_used"] == 165 and r["tss"] == pytest.approx(100)


def test_hr_fallback_when_no_ftp():
    r = score_activity({"moving_seconds": 3600, "normalized_power": 250, "hr_histogram": {165: 3600}},
                       {**TH, "ftp": None})
    assert r["tss_method"] == "hr"


def test_unscored_reasons():
    r = score_activity({"moving_seconds": 3600}, TH)
    assert r["tss"] is None and r["unscored_reason"] == "no_data" and r["relative_effort"] is None
    r = score_activity({"moving_seconds": 3600, "hr_histogram": {150: 60}}, {"ftp": None, "threshold_hr": None, "max_hr": None})
    assert r["unscored_reason"] == "no_threshold"
    r = score_activity({"moving_seconds": 3600, "normalized_power": 200}, {**TH, "ftp": None})
    assert r["unscored_reason"] == "no_threshold"


# --- 3.5 PMC ---
def _daily(d):
    return pd.Series(d, dtype=float)


def test_single_day():
    df = daily_pmc(_daily({date(2026, 1, 1): 100}), today=date(2026, 1, 1))
    r = df.iloc[0]
    assert len(df) == 1
    assert r.ctl == pytest.approx(100 / 42, abs=0.01) and r.atl == pytest.approx(100 / 7, abs=0.01)
    assert r.tsb == pytest.approx(r.ctl - r.atl)


def test_rest_decay():
    s = _daily({date(2026, 1, 1) + timedelta(days=i): 80 for i in range(28)})
    df = daily_pmc(s, today=date(2026, 1, 28) + timedelta(days=14))
    last, peak = df.iloc[-1], df.iloc[27]
    assert last.atl < peak.atl * 0.2          # ATL falls fast
    assert last.ctl > peak.ctl * 0.6          # CTL falls slowly
    assert last.tsb > peak.tsb


def test_zero_fill_to_today_and_between():
    df = daily_pmc(_daily({date(2026, 1, 1): 50, date(2026, 1, 4): 50}), today=date(2026, 1, 11))
    assert len(df) == 11 and df["date"].iloc[-1] == date(2026, 1, 11)
    assert df.loc[1, "tss"] == 0 and df.loc[1, "atl"] < df.loc[0, "atl"]


def test_empty():
    assert daily_pmc(pd.Series(dtype=float)).empty


def test_windowing_matches_full_history():
    s = _daily({date(2026, 1, 1) + timedelta(days=i): 60 for i in range(0, 120, 2)})
    full = daily_pmc(s, today=date(2026, 5, 1))
    w = window(full, date(2026, 3, 1), date(2026, 3, 31))
    assert len(w) == 31
    merged = w.merge(full, on="date", suffixes=("", "_f"))
    assert np.allclose(merged.ctl, merged.ctl_f) and np.allclose(merged.atl, merged.atl_f)


def test_weekly_sums_monday_start():
    s = _daily({date(2026, 1, 5): 60, date(2026, 1, 7): 80, date(2026, 1, 11): 40, date(2026, 1, 12): 10})
    wk = weekly_load(daily_pmc(s, today=date(2026, 1, 12)))
    assert list(wk["week_start"]) == [date(2026, 1, 5), date(2026, 1, 12)]
    assert list(wk["tss"]) == [180, 10]


# --- running is scored by HR even with power ---
def test_running_ignores_power_and_uses_hr():
    s = {"moving_seconds": 7200, "normalized_power": 350, "hr_histogram": {145: 7200}}
    ride = score_activity(s, TH, "cycling")
    run = score_activity(s, TH, "running")
    assert ride["tss_method"] == "power" and ride["tss"] > 300          # (350/250)^2 x 2 h
    assert run["tss_method"] == "hr" and run["thr_hr_used"] == 165 and run["ftp_used"] is None
    assert run["tss"] == pytest.approx(2 * 40)                           # 145/165 = 88% -> zone 2, 2 h
    assert score_activity(s, TH)["tss_method"] == "power"                # sport unknown: unchanged


def test_running_with_only_power_is_unscored():
    r = score_activity({"moving_seconds": 3600, "normalized_power": 300}, TH, "running")
    assert r["tss"] is None and r["unscored_reason"] == "no_data"


def test_running_without_threshold_hr_is_not_rescued_by_ftp():
    r = score_activity({"moving_seconds": 3600, "normalized_power": 300, "hr_histogram": {150: 3600}},
                       {**TH, "threshold_hr": None}, "running")
    assert r["tss"] is None and r["unscored_reason"] == "no_threshold"


def test_scoring_uses_configured_zone_edges_else_max_hr():
    s = {"moving_seconds": 3600, "hr_histogram": {150: 3600}}
    configured = score_activity(s, {"ftp": None, "threshold_hr": 165, "max_hr": None}, "running", EDGES)
    assert configured["relative_effort"] == pytest.approx(60 * 2.1) and configured["max_hr_used"] is None
    derived = score_activity(s, TH, "running")                                 # max HR 190 -> edges 120/152/160/171
    assert derived["relative_effort"] == pytest.approx(60 * 0.3) and derived["max_hr_used"] == 190
    none = score_activity(s, {"ftp": None, "threshold_hr": 165, "max_hr": None}, "running")
    assert none["relative_effort"] is None                                     # no zones and no max HR
