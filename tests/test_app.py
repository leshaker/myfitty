import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from myfitty import db
from myfitty.rescore import save_threshold

APP = str(Path(__file__).parent.parent / "myfitty" / "app.py")


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "fit").mkdir()
    monkeypatch.setenv("MYFITTY_FIT_DIR", str(tmp_path / "fit"))
    monkeypatch.setenv("MYFITTY_DB", str(tmp_path / "t.duckdb"))
    monkeypatch.setenv("MYFITTY_SAMPLES_DIR", str(tmp_path / "samples"))
    return tmp_path


def recent(days_ago):
    return datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=days_ago)


def seed(env, rows):
    today = date.today()
    with db.connect(env / "t.duckdb") as con:
        for i, (days_ago, sport, tss) in enumerate(rows):
            d = today - timedelta(days=days_ago)
            con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, moving_seconds, tss, "
                        "tss_method) VALUES (?, ?, ?, ?, 3600, ?, 'power')", [f"{d} 08:00:00", d, f"s{i}", sport, tss])


def run(env=None):
    st_app = AppTest.from_file(APP, default_timeout=60).run()
    assert not st_app.exception, st_app.exception
    return st_app


def charts(at):
    return at.get("vega_lite_chart")


def chart_data_max(chart, field):
    import pyarrow as pa
    return max(pa.ipc.open_stream(ds.data.data).read_all().to_pandas()[field].max() for ds in chart.proto.datasets)


def test_empty_state(env):
    at = run()
    assert any("No activities yet" in i.value for i in at.info)
    assert len(charts(at)) == 0


def test_charts_render_and_sport_filter_updates_them(env):
    seed(env, [(20, "cycling", 100), (10, "cycling", 120), (5, "running", 40)])
    at = run()
    assert len(charts(at)) == 4                               # PMC, form, weekly TSS, weekly effort
    assert len(at.dataframe[0].value) == 3
    combined = chart_data_max(charts(at)[2], "tss")
    at.selectbox[0].select("running").run()
    assert not at.exception
    assert len(charts(at)) == 4 and len(at.dataframe[0].value) == 1
    assert chart_data_max(charts(at)[2], "tss") < combined


def test_scan_on_open_imports_fit_files(env):
    from tests import fitgen
    p = env / "fit" / "a.fit"
    p.write_bytes(fitgen.ride_power_hr(start=recent(5)))
    os.utime(p, (time.time() - 3600,) * 2)
    at = run()
    assert not at.exception and len(at.dataframe[0].value) == 1
    # a file added later is picked up by the Import now button
    q = env / "fit" / "b.fit"
    q.write_bytes(fitgen.run_hr_only(start=recent(3)))
    os.utime(q, (time.time() - 3600,) * 2)
    at.button(key="import_now").click().run()
    assert len(at.dataframe[0].value) == 2


def seed_unscored(env, npw=250, days_ago=5):
    d = date.today() - timedelta(days=days_ago)
    with db.connect(env / "t.duckdb") as con:
        con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, moving_seconds, "
                    "normalized_power, unscored_reason) VALUES (?, ?, 's', 'cycling', 3600, ?, 'no_threshold')",
                    [f"{d} 08:00:00", d, npw])


def submit(at, metric, eff, value):
    at.selectbox(key="th_metric").select(metric)
    at.date_input(key="th_date").set_value(eff)
    at.number_input(key="th_value").set_value(value)
    at.button(key="th_submit").click().run()
    return at


def test_threshold_form_stores_and_rescores(env):
    seed_unscored(env)
    at = run()
    assert at.dataframe[0].value["TSS"].isna().all()
    submit(at, "ftp", date.today() - timedelta(days=30), 250.0)
    assert not at.exception and not at.error
    with db.connect(env / "t.duckdb") as con:
        assert con.execute("SELECT tss, tss_method FROM activities").fetchone() == (pytest.approx(100), "power")
        assert db.list_thresholds(con)[0][1:] == (date.today() - timedelta(days=30), 250.0)
    assert any("rescored 1" in s.value for s in at.success)
    assert at.dataframe[0].value["TSS"].iloc[0] == pytest.approx(100)  # table reflects the change


def test_threshold_form_rejects_invalid_value(env):
    seed_unscored(env)
    at = run()
    submit(at, "ftp", date.today(), 0.0)
    assert any("positive" in e.value for e in at.error)
    with db.connect(env / "t.duckdb") as con:
        assert db.list_thresholds(con) == []


def test_threshold_available_before_any_import(env):
    at = run()  # empty database
    submit(at, "max_hr", date.today(), 190.0)
    assert not at.error
    with db.connect(env / "t.duckdb") as con:
        assert db.threshold_on(con, "max_hr", date.today()) == 190


def test_threshold_delete_rescores(env):
    seed_unscored(env)
    at = run()
    submit(at, "ftp", date.today() - timedelta(days=30), 250.0)
    at.button(key="th_delete").click().run()
    assert not at.exception
    with db.connect(env / "t.duckdb") as con:
        assert db.list_thresholds(con) == []
        assert con.execute("SELECT tss, unscored_reason FROM activities").fetchone() == (None, "no_threshold")


def test_config_thresholds_loaded_at_start(env):
    (env / "myfitty.toml").write_text(
        f'[[thresholds]]\nmetric = "ftp"\nfrom = {date.today() - timedelta(days=30)}\nvalue = 250\n')
    seed_unscored(env)
    at = run()
    with db.connect(env / "t.duckdb") as con:
        assert db.list_thresholds(con)[0][2] == 250
        assert con.execute("SELECT tss FROM activities").fetchone()[0] == pytest.approx(100)
    assert at.dataframe[0].value["TSS"].iloc[0] == pytest.approx(100)


def test_activity_table_shows_local_time_and_whole_numbers(env):
    d = date.today() - timedelta(days=3)
    utc = datetime(d.year, d.month, d.day, 14, 25, tzinfo=timezone.utc)
    with db.connect(env / "t.duckdb") as con:
        con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, moving_seconds, tss, "
                    "tss_method, relative_effort) VALUES (?, ?, 's', 'cycling', 3600, 52.4889, 'power', 439.5833)",
                    [utc.replace(tzinfo=None), utc.astimezone().date()])
    at = run()
    row = at.dataframe[0].value.iloc[0]
    assert row["when"] == utc.astimezone().strftime("%Y-%m-%d %H:%M")      # local, not UTC
    import json
    cols = json.loads(at.dataframe[0].proto.columns)                       # whole-number display for the scores
    assert cols["TSS"]["type_config"]["format"] == "%.0f"
    assert cols["relative effort"]["type_config"]["format"] == "%.0f"


def test_weekly_chart_has_one_band_per_week(env):
    seed(env, [(40, "cycling", 100), (20, "cycling", 120), (5, "running", 40)])
    at = run()
    spec = charts(at)[2].proto.spec
    assert '"field": "week"' in spec and '"type": "ordinal"' in spec
    assert '"type": "temporal"' not in spec.split('"tooltip"')[0]            # x is no longer a time axis


def pmc_metrics(at):
    import pyarrow as pa
    ds = charts(at)[0].proto.datasets[0].data.data
    return set(pa.ipc.open_stream(ds).read_all().to_pandas()["metric"])


def test_series_can_be_shown_and_hidden_independently(env):
    seed(env, [(20, "cycling", 100), (5, "cycling", 120)])
    at = run()
    pills = at.get("button_group")[0]
    assert pills.value == ["Fitness (CTL)", "Fatigue (ATL)"]                 # both visible by default
    assert pmc_metrics(at) == {"Fitness (CTL)", "Fatigue (ATL)"}

    pills.set_value(["Fitness (CTL)"]).run()                                  # hide ATL only
    assert not at.exception and pmc_metrics(at) == {"Fitness (CTL)"}
    at.get("button_group")[0].set_value(["Fitness (CTL)", "Fatigue (ATL)"]).run()   # show it again: both
    assert pmc_metrics(at) == {"Fitness (CTL)", "Fatigue (ATL)"}
    at.get("button_group")[0].set_value(["Fatigue (ATL)"]).run()              # the other one alone
    assert pmc_metrics(at) == {"Fatigue (ATL)"}

    at.get("button_group")[0].set_value([]).run()                             # none: no chart, a hint instead
    assert not at.exception and len(charts(at)) == 3                          # form + both weekly charts remain
    assert any("at least one series" in c.value for c in at.caption)


def rule_tooltip_titles(at):
    spec = json.loads(charts(at)[0].proto.spec)
    rule = next(l for l in spec["layer"] if (l["mark"] if isinstance(l["mark"], str) else l["mark"]["type"]) == "rule")
    return [t["title"] for t in rule["encoding"]["tooltip"]]


def test_tooltip_lists_every_visible_series_at_once(env):
    seed(env, [(20, "cycling", 100), (5, "cycling", 120)])
    at = run()
    assert rule_tooltip_titles(at) == ["Date", "Fitness (CTL)", "Fatigue (ATL)", "Form (TSB)"]
    at.get("button_group")[0].set_value(["Fatigue (ATL)"]).run()
    assert rule_tooltip_titles(at) == ["Date", "Fatigue (ATL)", "Form (TSB)"]


def test_weekly_relative_effort_chart_follows_the_sport_filter(env):
    d1, d2 = date.today() - timedelta(days=9), date.today() - timedelta(days=2)
    with db.connect(env / "t.duckdb") as con:
        for i, (d, sport, effort) in enumerate([(d1, "cycling", 200.0), (d2, "running", 80.0)]):
            con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, moving_seconds, "
                        "relative_effort) VALUES (?, ?, ?, ?, 3600, ?)", [f"{d} 08:00:00", d, f"s{i}", sport, effort])
    at = run()
    assert chart_data_max(charts(at)[3], "effort") >= 200
    at.selectbox[0].select("running").run()
    assert not at.exception and chart_data_max(charts(at)[3], "effort") == 80
