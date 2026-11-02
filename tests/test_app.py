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


def pills(at):
    """The CTL/ATL series pills (the View switch is a button_group too, so look them up by key)."""
    return next(b for b in at.get("button_group") if b.key == "series_pills")


def pmc_metrics(at):
    import pyarrow as pa
    ds = charts(at)[0].proto.datasets[0].data.data
    return set(pa.ipc.open_stream(ds).read_all().to_pandas()["metric"])


def test_series_can_be_shown_and_hidden_independently(env):
    seed(env, [(20, "cycling", 100), (5, "cycling", 120)])
    at = run()
    pills_el = pills(at)
    assert pills_el.value == ["Fitness (CTL)", "Fatigue (ATL)"]                 # both visible by default
    assert pmc_metrics(at) == {"Fitness (CTL)", "Fatigue (ATL)"}

    pills_el.set_value(["Fitness (CTL)"]).run()                                  # hide ATL only
    assert not at.exception and pmc_metrics(at) == {"Fitness (CTL)"}
    pills(at).set_value(["Fitness (CTL)", "Fatigue (ATL)"]).run()   # show it again: both
    assert pmc_metrics(at) == {"Fitness (CTL)", "Fatigue (ATL)"}
    pills(at).set_value(["Fatigue (ATL)"]).run()              # the other one alone
    assert pmc_metrics(at) == {"Fatigue (ATL)"}

    pills(at).set_value([]).run()                             # none: no chart, a hint instead
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
    pills(at).set_value(["Fatigue (ATL)"]).run()
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


# --- heatmap view ---
def seed_route(env, days_ago, sport, stretches, sub_sport=None, serial=None):
    d = date.today() - timedelta(days=days_ago)
    with db.connect(env / "t.duckdb") as con:
        con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, sub_sport, moving_seconds, tss) "
                    "VALUES (?, ?, ?, ?, ?, 3600, 50)", [f"{d} 08:00:00", d, serial or f"h{days_ago}{sport}", sport, sub_sport])
        aid = con.execute("SELECT max(id) FROM activities").fetchone()[0]
        con.execute("INSERT INTO activity_tracks VALUES (?, ?, ?)",
                    [aid, json.dumps(stretches), sum(len(s) for s in stretches)])


def view_switch(at):
    return next(b for b in at.get("button_group") if b.key == "view")


def open_heatmap(at):
    view_switch(at).set_value("Heatmap").run()
    assert not at.exception, at.exception
    return at


def deck(at):
    els = at.get("deck_gl_json_chart")
    return json.loads(els[0].proto.json) if els else None


FREIBURG = [[7.80, 47.98], [7.85, 48.00], [7.90, 48.02]]
BERLIN = [[13.30, 52.50], [13.40, 52.52], [13.45, 52.55]]


def test_training_view_has_no_map_and_heatmap_view_has_no_training_charts(env):
    seed(env, [(20, "cycling", 100), (5, "cycling", 120)])
    seed_route(env, 5, "cycling", [FREIBURG], serial="m1")
    at = run()
    assert view_switch(at).value == "Training"
    assert len(charts(at)) == 4 and deck(at) is None                      # as before, and no map is built
    open_heatmap(at)
    assert len(charts(at)) == 0 and deck(at) is not None                  # only the map; no training charts
    view_switch(at).set_value("Training").run()
    assert len(charts(at)) == 4 and deck(at) is None


def layer(at):
    return deck(at)["layers"][0]


def route_paths(at):
    return [d["path"] for d in layer(at)["data"]]


def date_range(at):
    return next(d for d in at.date_input if d.label == "Date range")


def test_routes_view_draws_thin_translucent_lines(env):
    seed_route(env, 5, "cycling", [FREIBURG], serial="m1")
    at = open_heatmap(run())
    lay = layer(at)
    assert lay["@@type"] == "PathLayer"
    assert lay["widthMinPixels"] <= 2                                      # thin
    assert all(d["color"][3] < 128 for d in lay["data"])                   # translucent, so overlaps add up
    assert route_paths(at) == [FREIBURG]


def test_all_sports_are_coloured_by_sport_with_a_legend(env):
    seed_route(env, 5, "cycling", [FREIBURG], serial="c")
    seed_route(env, 4, "running", [BERLIN], serial="r")
    at = open_heatmap(run())
    colours = {tuple(d["color"][:3]) for d in layer(at)["data"]}
    assert colours == {(42, 120, 214), (235, 104, 52)}
    legend = " ".join(m.value for m in at.markdown)
    assert "cycling" in legend and "running" in legend and "#2a78d6" in legend and "#eb6834" in legend


def test_one_sport_uses_a_single_colour_and_no_legend(env):
    seed_route(env, 5, "cycling", [FREIBURG], serial="c")
    seed_route(env, 4, "running", [BERLIN], serial="r")
    at = open_heatmap(run())
    at.selectbox[0].select("running").run()
    assert not at.exception
    assert route_paths(at) == [BERLIN]
    assert {tuple(d["color"][:3]) for d in layer(at)["data"]} == {(235, 104, 52)}
    assert "#2a78d6" not in " ".join(m.value for m in at.markdown)


def test_date_range_limits_the_routes(env):
    seed_route(env, 100, "cycling", [FREIBURG], serial="old")
    seed_route(env, 5, "cycling", [BERLIN], serial="new")
    at = open_heatmap(run())                                               # default range: last 180 days
    assert sorted(map(str, route_paths(at))) == sorted(map(str, [FREIBURG, BERLIN]))
    month = date.today() - timedelta(days=30)
    date_range(at).set_value((month, date.today())).run()
    assert not at.exception and route_paths(at) == [BERLIN]


def test_virtual_and_indoor_activities_stay_off_the_map_but_count_in_the_load(env):
    seed_route(env, 5, "cycling", [FREIBURG], serial="real")
    seed_route(env, 4, "cycling", [], sub_sport="virtual_activity", serial="zwift")     # no route stored for it
    seed_route(env, 3, "cycling", [], sub_sport="indoor_cycling", serial="trainer")
    at = open_heatmap(run())
    assert route_paths(at) == [FREIBURG]
    assert all(lat > 0 for path in route_paths(at) for _, lat in path)                  # no game-world coordinates
    view_switch(at).set_value("Training").run()
    table = at.dataframe[0].value
    assert len(table) == 3 and table["TSS"].sum() == 150                                  # all three still count in the load


def test_density_view_uses_evenly_spaced_points_and_switching_keeps_the_selection(env):
    from myfitty import geo
    seed_route(env, 5, "cycling", [FREIBURG], serial="c")
    seed_route(env, 4, "running", [BERLIN], serial="r")
    at = open_heatmap(run())
    at.selectbox[0].select("running").run()
    routes_view = deck(at)["initialViewState"]
    assert layer(at)["@@type"] == "PathLayer"

    at.radio(key="heat_mode").set_value("Density").run()
    assert not at.exception
    lay = layer(at)
    assert lay["@@type"] == "HeatmapLayer" and lay["aggregation"] == "SUM"
    assert lay["getPosition"] == "@@=d"                                     # one prefix: "@@=@@=d" fails in the browser
    assert len(lay["data"]) == len(geo.density_points([BERLIN], 100))        # only the selected sport, spaced by distance
    assert all(abs(lon - 13.4) < 0.1 and abs(lat - 52.5) < 0.1 for lon, lat in lay["data"])
    assert at.selectbox[0].value == "running"                                  # filters kept
    view = deck(at)["initialViewState"]
    assert (view["longitude"], view["latitude"], view["zoom"]) == (
        routes_view["longitude"], routes_view["latitude"], routes_view["zoom"])   # same map position

    at.radio(key="heat_mode").set_value("Routes").run()
    assert layer(at)["@@type"] == "PathLayer" and route_paths(at) == [BERLIN]


def test_density_payload_stays_small_for_a_long_history(env):
    import numpy as np
    from myfitty import geo
    i = np.arange(0, 3000)                                                    # a ~330 km route
    long_route = np.column_stack([8.0 + 0.00005 * i, 48.0 + 0.001 * i]).round(5).tolist()
    for n in range(40):
        seed_route(env, 1 + n, "cycling", [long_route], serial=f"l{n}")
    at = open_heatmap(run())
    at.radio(key="heat_mode").set_value("Density").run()
    assert len(layer(at)["data"]) == 40 * len(geo.density_points([long_route], 100))
    assert len(at.get("deck_gl_json_chart")[0].proto.json) < 5_000_000


def view_state(at):
    v = deck(at)["initialViewState"]
    return v["longitude"], v["latitude"], v["zoom"]


def contains(view, paths, width=1100, height=600):
    from myfitty import geo
    lon, lat, zoom = view
    scale = geo.TILE * 2 ** zoom
    cx, cy = (lon + 180) / 360, geo._merc_y(lat)
    return all(abs(((lo + 180) / 360 - cx) * scale) <= width / 2 and abs((geo._merc_y(la) - cy) * scale) <= height / 2
               for path in paths for lo, la in path)


def test_map_fits_the_routes_and_moves_when_the_selection_changes_region(env):
    seed_route(env, 100, "cycling", [FREIBURG], serial="old")
    seed_route(env, 5, "cycling", [BERLIN], serial="new")
    at = open_heatmap(run())
    both = view_state(at)
    assert contains(both, [FREIBURG, BERLIN])                              # everything in the selection is in view
    assert both[2] < 8                                                      # zoomed out to span both cities
    date_range(at).set_value((date.today() - timedelta(days=30), date.today())).run()
    berlin = view_state(at)
    assert contains(berlin, [BERLIN]) and abs(berlin[0] - 13.4) < 0.1 and abs(berlin[1] - 52.5) < 0.1
    assert berlin[2] > both[2] + 2                                          # and zoomed right in


def test_basemap_can_be_switched_off(env):
    seed_route(env, 5, "cycling", [FREIBURG], serial="c")
    at = open_heatmap(run())
    assert "cartocdn" in deck(at)["mapStyle"]                               # on by default: a tile style
    at.toggle(key="basemap").set_value(False).run()
    style = deck(at)["mapStyle"]                                            # Streamlit would pick a themed tile
    assert not at.exception and style["layers"] == [] and style["sources"] == {}   # basemap itself: send an empty style
    assert route_paths(at) == [FREIBURG]                                    # the routes are still drawn
    at.toggle(key="basemap").set_value(True).run()
    assert "cartocdn" in deck(at)["mapStyle"]


def test_empty_selection_explains_what_is_shown(env):
    seed_route(env, 5, "cycling", [], sub_sport="virtual_activity", serial="zwift")
    seed_route(env, 4, "cycling", [], sub_sport="indoor_cycling", serial="trainer")
    at = open_heatmap(run())
    assert deck(at) is None                                                 # no map is drawn
    text = " ".join(i.value for i in at.info)
    assert "No routes found" in text and "outdoor activities with GPS" in text and "wider date range" in text


def test_empty_database_shows_the_usual_empty_state_and_no_map(env):
    at = run()
    assert any("No activities yet" in i.value for i in at.info) and deck(at) is None
