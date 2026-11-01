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


def test_weekly_effort_sums_per_week_and_follows_sport(con):
    def add_effort(d, sport, effort, serial):
        con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, relative_effort) "
                    "VALUES (?, ?, ?, ?, ?)", [f"{d} 08:00:00", d, serial, sport, effort])
    add_effort(date(2026, 1, 5), "cycling", 120, "a")
    add_effort(date(2026, 1, 7), "running", 60, "b")
    add_effort(date(2026, 1, 8), "cycling", None, "c")                 # no heart rate: counts as zero
    add_effort(date(2026, 1, 13), "running", 40, "d")
    today = date(2026, 1, 14)
    wk = queries.weekly_effort(con, today=today)
    assert list(wk["week_start"]) == [date(2026, 1, 5), date(2026, 1, 12)] and list(wk["effort"]) == [180, 40]
    assert list(queries.weekly_effort(con, "running", today=today)["effort"]) == [60, 40]
    assert queries.weekly_effort(con, "swimming", today=today).empty


def test_weekly_effort_empty_database(con):
    assert queries.weekly_effort(con).empty


# --- routes ---
def add_route(con, d, sport, stretches, sub_sport=None, serial=None):
    con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, sub_sport) VALUES (?, ?, ?, ?, ?)",
                [f"{d} 08:00:00", d, serial or f"r{sport}{d}", sport, sub_sport])
    aid = con.execute("SELECT max(id) FROM activities").fetchone()[0]
    import json as _json
    con.execute("INSERT INTO activity_tracks VALUES (?, ?, ?)",
                [aid, _json.dumps(stretches), sum(len(s) for s in stretches)])
    return aid


A = [[8.0, 48.0], [8.01, 48.01]]
B = [[8.02, 48.02], [8.03, 48.03]]


def test_routes_one_row_per_stretch_with_sport_and_date(con):
    aid = add_route(con, date(2026, 1, 5), "cycling", [A, B])
    df = queries.routes(con)
    assert list(df.columns) == ["activity_id", "sport", "local_date", "stretch"]
    assert len(df) == 2 and set(df["activity_id"]) == {aid} and set(df["sport"]) == {"cycling"}
    assert df["stretch"].iloc[0] == A and df["stretch"].iloc[1] == B and df["local_date"].iloc[0] == date(2026, 1, 5)


def test_routes_sport_and_date_filters(con):
    add_route(con, date(2026, 1, 5), "cycling", [A])
    add_route(con, date(2026, 2, 5), "running", [B])
    assert set(queries.routes(con, sport="running")["sport"]) == {"running"}
    assert set(queries.routes(con, start=date(2026, 2, 1))["sport"]) == {"running"}
    assert set(queries.routes(con, end=date(2026, 1, 31))["sport"]) == {"cycling"}
    assert len(queries.routes(con, start=date(2026, 3, 1))) == 0


def test_routes_leave_out_activities_without_a_route(con):
    add_route(con, date(2026, 1, 5), "cycling", [A])
    add_route(con, date(2026, 1, 6), "cycling", [], sub_sport="indoor_cycling")     # zero-point row
    add_route(con, date(2026, 1, 7), "cycling", [], sub_sport="virtual_activity")
    con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport) "
                "VALUES ('2026-01-08 08:00:00', '2026-01-08', 'norow', 'running')")  # never handled: no row at all
    df = queries.routes(con)
    assert len(df) == 1 and list(df["sport"]) == ["cycling"]


def test_routes_do_not_change_the_training_load(con):
    add(con, date(2026, 1, 5), "cycling", 80)                                       # a virtual ride still counts
    add_route(con, date(2026, 1, 5), "cycling", [], sub_sport="virtual_activity", serial="v")
    assert list(queries.pmc(con, today=date(2026, 1, 5))["tss"]) == [80]


def test_routes_empty_database(con):
    df = queries.routes(con)
    assert df.empty and list(df.columns) == ["activity_id", "sport", "local_date", "stretch"]
