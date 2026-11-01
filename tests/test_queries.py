from datetime import date

import numpy as np
import pytest

from myfitty import db, queries


@pytest.fixture
def con(tmp_path):
    with db.connect(tmp_path / "t.duckdb") as c:
        yield c


def add(con, d, sport, tss, serial=None):
    con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, tss) VALUES (?, ?, ?, ?, ?)",
                [f"{d} 08:00:00", d, serial or f"{sport}{d}{tss}", sport, tss])


def test_sports(con):
    assert queries.sports(con) == []
    add(con, date(2026, 1, 1), "running", 50)
    add(con, date(2026, 1, 2), "cycling", 70)
    assert queries.sports(con) == ["cycling", "running"]


def test_combined_vs_sport_filter(con):
    add(con, date(2026, 1, 1), "running", 40)
    add(con, date(2026, 1, 1), "cycling", 60)
    add(con, date(2026, 1, 2), "cycling", 100)
    today = date(2026, 1, 2)
    both = queries.pmc(con, today=today)
    assert list(both["tss"]) == [100, 100]
    run = queries.pmc(con, "running", today=today)
    assert list(run["tss"]) == [40, 0]            # cycling contributes nothing
    assert run["ctl"].iloc[0] == pytest.approx(40 / 42) and run["atl"].iloc[0] == pytest.approx(40 / 7)


def test_unscored_counts_zero_but_starts_series(con):
    add(con, date(2026, 1, 1), "cycling", None)
    df = queries.pmc(con, today=date(2026, 1, 3))
    assert list(df["tss"]) == [0, 0, 0]


def test_windowed_ctl_equals_full_history(con):
    for i in range(0, 100, 3):
        add(con, date.fromordinal(date(2026, 1, 1).toordinal() + i), "cycling", 70)
    today = date(2026, 6, 1)
    full = queries.pmc(con, today=today)
    win = queries.pmc(con, start=date(2026, 3, 1), end=date(2026, 3, 31), today=today)
    assert len(win) == 31
    ref = full[full["date"].isin(set(win["date"]))].reset_index(drop=True)
    assert np.allclose(win["ctl"], ref["ctl"]) and np.allclose(win["atl"], ref["atl"])


def test_weekly(con):
    add(con, date(2026, 1, 5), "cycling", 60)
    add(con, date(2026, 1, 7), "running", 80)
    add(con, date(2026, 1, 11), "cycling", 40)
    wk = queries.weekly(con, today=date(2026, 1, 11))
    assert list(wk["tss"]) == [180]
    assert list(queries.weekly(con, "running", today=date(2026, 1, 11))["tss"]) == [80]


def test_empty_database(con):
    assert queries.pmc(con).empty and queries.weekly(con).empty and queries.activities(con).empty


def test_activities_filters(con):
    add(con, date(2026, 1, 1), "running", 40)
    add(con, date(2026, 2, 1), "cycling", 60)
    assert len(queries.activities(con)) == 2
    assert list(queries.activities(con, sport="running")["sport"]) == ["running"]
    assert len(queries.activities(con, start=date(2026, 1, 15))) == 1
    assert len(queries.activities(con, end=date(2026, 1, 15))) == 1
