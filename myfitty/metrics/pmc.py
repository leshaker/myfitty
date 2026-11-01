from datetime import date, timedelta

import pandas as pd

from myfitty.metrics.constants import ATL_DAYS, CTL_DAYS


def daily_pmc(daily_tss: pd.Series, today: date | None = None) -> pd.DataFrame:
    """Daily TSS, CTL, ATL and TSB.

    daily_tss: TSS summed per local date (index of datetime.date). The series runs from the first
    date with data through `today` (default: current local date), zero-filled, starting from 0.
    CTL/ATL are exponentially weighted averages (42 / 7 day constants); TSB = CTL - ATL (same day).
    """
    cols = ["date", "tss", "ctl", "atl", "tsb"]
    if daily_tss is None or len(daily_tss) == 0:
        return pd.DataFrame(columns=cols)
    today = today or date.today()
    s = daily_tss.copy()
    s.index = pd.to_datetime(s.index)
    start = s.index.min()
    end = max(pd.Timestamp(today), s.index.max())
    s = s.groupby(level=0).sum().reindex(pd.date_range(start, end, freq="D"), fill_value=0.0)

    ctl = atl = 0.0
    rows = []
    for d, tss in s.items():
        ctl += (tss - ctl) / CTL_DAYS
        atl += (tss - atl) / ATL_DAYS
        rows.append((d.date(), float(tss), ctl, atl, ctl - atl))
    return pd.DataFrame(rows, columns=cols)


def weekly_load(pmc: pd.DataFrame) -> pd.DataFrame:
    """Total TSS per ISO week (Monday start) from a daily frame."""
    if pmc.empty:
        return pd.DataFrame(columns=["week_start", "tss"])
    d = pd.to_datetime(pmc["date"])
    week = (d - pd.to_timedelta(d.dt.day_of_week, unit="D")).dt.date
    return pmc.assign(week_start=week).groupby("week_start", as_index=False)["tss"].sum()


def window(pmc: pd.DataFrame, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    """Slice a computed series; values were computed from full history so don't depend on the range."""
    out = pmc
    if start is not None:
        out = out[out["date"] >= start]
    if end is not None:
        out = out[out["date"] <= end]
    return out.reset_index(drop=True)
