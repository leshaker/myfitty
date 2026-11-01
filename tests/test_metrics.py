from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from myfitty.metrics.pmc import daily_pmc, weekly_load, window
from myfitty.metrics.scoring import score_activity
from myfitty.metrics.trimp import trimp
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


# --- 3.3 TRIMP ---
def test_trimp_30_min_zone3():
    assert trimp({150: 1800}, 200) == pytest.approx(90)  # 75% of max


def test_trimp_below_zone1_and_top_zone():
    assert trimp({90: 3600}, 200) == 0
    assert trimp({200: 600}, 200) == pytest.approx(50)  # 10 min x 5


def test_trimp_no_hr():
    assert trimp(None, 200) is None and trimp({}, 200) is None and trimp({150: 60}, None) is None


# --- 3.4 scoring selector ---
TH = {"ftp": 250, "threshold_hr": 165, "max_hr": 190}


def test_power_wins_when_both():
    r = score_activity({"moving_seconds": 3600, "normalized_power": 250, "hr_histogram": {150: 3600}}, TH)
    assert r["tss"] == pytest.approx(100) and r["tss_method"] == "power"
    assert r["ftp_used"] == 250 and r["thr_hr_used"] is None and r["max_hr_used"] == 190
    assert r["trimp"] is not None and r["unscored_reason"] is None


def test_hr_fallback_without_power():
    r = score_activity({"moving_seconds": 3600, "hr_histogram": {165: 3600}}, TH)
    assert r["tss_method"] == "hr" and r["thr_hr_used"] == 165 and r["tss"] == pytest.approx(100)


def test_hr_fallback_when_no_ftp():
    r = score_activity({"moving_seconds": 3600, "normalized_power": 250, "hr_histogram": {165: 3600}},
                       {**TH, "ftp": None})
    assert r["tss_method"] == "hr"


def test_unscored_reasons():
    r = score_activity({"moving_seconds": 3600}, TH)
    assert r["tss"] is None and r["unscored_reason"] == "no_data" and r["trimp"] is None
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
