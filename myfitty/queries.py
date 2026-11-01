"""Read-side queries returning DataFrames for the UI. No Streamlit imports."""
from datetime import date

import pandas as pd

from myfitty.metrics import pmc as pmc_calc


def sports(con) -> list[str]:
    return [s for (s,) in con.execute("SELECT DISTINCT sport FROM activities ORDER BY sport").fetchall()]


def activities(con, sport: str | None = None, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    q = ("SELECT id, start_time, local_date, sport, sub_sport, moving_seconds, distance_m, avg_hr, avg_power, "
         "normalized_power, tss, tss_method, trimp, ftp_used, thr_hr_used, max_hr_used, unscored_reason, "
         "sample_path FROM activities WHERE true")
    args = []
    if sport:
        q += " AND sport = ?"
        args.append(sport)
    if start:
        q += " AND local_date >= ?"
        args.append(start)
    if end:
        q += " AND local_date <= ?"
        args.append(end)
    return con.execute(q + " ORDER BY start_time DESC", args).df()


def daily_tss(con, sport: str | None = None) -> pd.Series:
    """TSS summed per local date; unscored activities count as zero."""
    q = "SELECT local_date, sum(coalesce(tss, 0)) AS tss FROM activities"
    args = []
    if sport:
        q += " WHERE sport = ?"
        args.append(sport)
    rows = con.execute(q + " GROUP BY local_date ORDER BY local_date", args).fetchall()
    return pd.Series({d: float(t) for d, t in rows}, dtype="float64")


def pmc(con, sport: str | None = None, start: date | None = None, end: date | None = None,
        today: date | None = None) -> pd.DataFrame:
    """CTL/ATL/TSB always computed from the full history, then sliced to [start, end]."""
    return pmc_calc.window(pmc_calc.daily_pmc(daily_tss(con, sport), today), start, end)


def weekly(con, sport: str | None = None, start: date | None = None, end: date | None = None,
           today: date | None = None) -> pd.DataFrame:
    return pmc_calc.weekly_load(pmc(con, sport, start, end, today))
