import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from myfitty import db
from myfitty.config import ConfigError, ThresholdEntry, load_config
from myfitty.rescore import seed_thresholds
from tests import fitgen

TOML = """
fit_dir = "rides"
db_path = "state/x.duckdb"

[[thresholds]]
metric = "ftp"
from = 2020-12-07
value = 265

[[thresholds]]
metric = "ftp"
from = "2020-11-29"
value = 251

[[thresholds]]
metric = "max_hr"
from = 2020-11-29
value = 182
"""


def write(tmp_path, text=TOML, name="myfitty.toml"):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_no_file_uses_defaults(tmp_path):
    cfg = load_config()
    assert str(cfg.fit_dir) == "fit" and cfg.thresholds == ()
    assert str(cfg.db_path) == "data/myfitty.duckdb"


def test_file_in_cwd_is_loaded_with_paths_relative_to_it(tmp_path):
    write(tmp_path)
    cfg = load_config()
    assert cfg.fit_dir == tmp_path / "rides" or str(cfg.fit_dir) == "rides"
    assert cfg.db_path.name == "x.duckdb"
    # thresholds sorted by date; ISO strings and TOML dates both accepted
    assert cfg.thresholds == (
        ThresholdEntry("ftp", date(2020, 11, 29), 251.0),
        ThresholdEntry("max_hr", date(2020, 11, 29), 182.0),
        ThresholdEntry("ftp", date(2020, 12, 7), 265.0))


def test_relative_paths_resolve_against_file_folder(tmp_path, monkeypatch):
    sub = tmp_path / "conf"
    sub.mkdir()
    write(sub, name="my.toml")
    monkeypatch.setenv("MYFITTY_CONFIG", str(sub / "my.toml"))
    assert load_config().fit_dir == sub / "rides"


def test_environment_overrides_file(tmp_path, monkeypatch):
    write(tmp_path)
    monkeypatch.setenv("MYFITTY_FIT_DIR", str(tmp_path / "other"))
    assert load_config().fit_dir == tmp_path / "other"


@pytest.mark.parametrize("text, msg", [
    ("[[thresholds]]\nmetric='ftp'\nvalue=250\n", "needs metric, from and value"),
    ("[[thresholds]]\nmetric='vo2'\nfrom=2020-01-01\nvalue=50\n", "unknown metric"),
    ("[[thresholds]]\nmetric='ftp'\nfrom=2020-01-01\nvalue=0\n", "positive"),
    ("[[thresholds]]\nmetric='ftp'\nfrom='soon'\nvalue=250\n", "date"),
    ("thresholds = 5\n", "array of tables"),
    ("fit_dir = \n", "cannot read"),
])
def test_invalid_config_is_rejected_with_message(tmp_path, text, msg):
    write(tmp_path, text)
    with pytest.raises(ConfigError, match=msg):
        load_config()


def test_missing_explicit_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MYFITTY_CONFIG", str(tmp_path / "nope.toml"))
    with pytest.raises(ConfigError, match="missing"):
        load_config()


# --- seeding ---
@pytest.fixture
def con(tmp_path):
    with db.connect(tmp_path / "t.duckdb") as c:
        yield c


ENTRIES = (ThresholdEntry("ftp", date(2020, 11, 29), 251.0), ThresholdEntry("ftp", date(2021, 1, 17), 280.0))


def test_seed_inserts_and_is_idempotent(con):
    assert seed_thresholds(con, ENTRIES) == 2
    assert seed_thresholds(con, ENTRIES) == 0
    assert [(e[1], e[2]) for e in db.list_thresholds(con, "ftp")] == [(date(2020, 11, 29), 251), (date(2021, 1, 17), 280)]


def test_seed_never_overwrites_or_deletes_ui_edits(con):
    seed_thresholds(con, ENTRIES)
    db.set_threshold(con, "ftp", date(2020, 11, 29), 260)       # edited in the UI
    db.set_threshold(con, "ftp", date(2022, 1, 1), 290)         # added in the UI
    assert seed_thresholds(con, ENTRIES) == 0
    assert [e[2] for e in db.list_thresholds(con, "ftp")] == [260, 280, 290]


def test_seed_rescores_existing_activities(tmp_path):
    cfgdir = tmp_path
    (cfgdir / "fit").mkdir()
    p = cfgdir / "fit" / "a.fit"
    p.write_bytes(fitgen.ride_power_hr(start=datetime(2026, 3, 10, 7, tzinfo=timezone.utc)))
    os.utime(p, (time.time() - 3600,) * 2)
    from myfitty.config import Config
    from myfitty.ingest.importer import scan
    cfg = Config(cfgdir / "fit", cfgdir / "t.duckdb", cfgdir / "s")
    with db.connect(cfg.db_path) as con:
        scan(con, cfg)
        assert con.execute("SELECT tss FROM activities").fetchone()[0] is None
        seed_thresholds(con, ENTRIES)
        assert con.execute("SELECT tss, ftp_used FROM activities").fetchone()[1] == 280


def test_seed_rejects_entry_conflicting_with_stored_values(con):
    db.set_threshold(con, "max_hr", date(2020, 1, 1), 180)
    with pytest.raises(ValueError):
        seed_thresholds(con, (ThresholdEntry("threshold_hr", date(2020, 1, 1), 190.0),))


def test_cli_applies_config_and_reports_errors(tmp_path):
    (tmp_path / "fit").mkdir()
    write(tmp_path, 'fit_dir = "fit"\n[[thresholds]]\nmetric = "ftp"\nfrom = 2020-01-01\nvalue = 250\n')
    out = subprocess.run([sys.executable, "-m", "myfitty.ingest"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    with db.connect(tmp_path / "data" / "myfitty.duckdb") as con:
        assert db.threshold_on(con, "ftp", date(2021, 1, 1)) == 250
    write(tmp_path, "[[thresholds]]\nmetric='x'\nfrom=2020-01-01\nvalue=1\n")
    out = subprocess.run([sys.executable, "-m", "myfitty.ingest"], capture_output=True, text=True)
    assert out.returncode == 2 and "config error" in out.stderr


def test_zone_edges_are_read_and_optional(tmp_path):
    assert load_config().zone_edges is None
    write(tmp_path, "[relative_effort]\nzone_edges = [114, 146, 153, 163]\n")
    assert load_config().zone_edges == (114.0, 146.0, 153.0, 163.0)


@pytest.mark.parametrize("edges", ["[114, 146, 153]", "[114, 146, 153, 150]", "[0, 146, 153, 163]",
                                   "[114, 146, 153, \"x\"]", "163"])
def test_invalid_zone_edges_are_rejected(tmp_path, edges):
    write(tmp_path, f"[relative_effort]\nzone_edges = {edges}\n")
    with pytest.raises(ConfigError, match="zone_edges"):
        load_config()


def test_rescore_uses_the_configured_zone_edges(tmp_path):
    with db.connect(tmp_path / "t.duckdb") as con:
        con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, moving_seconds, hr_histogram) "
                    "VALUES ('2026-03-10 07:00:00', '2026-03-10', 'x', 'cycling', 3600, '{\"150\": 3600}')")
        db.set_threshold(con, "max_hr", date(2026, 1, 1), 190)           # default edges (120/152/160/171) -> Z2
        from myfitty.rescore import rescore
        rescore(con)
        assert con.execute("SELECT relative_effort FROM activities").fetchone()[0] == pytest.approx(60 * 0.3)
        write(tmp_path, "[relative_effort]\nzone_edges = [114, 146, 153, 163]\n")   # 150 bpm is Z3 here
        rescore(con)
        assert con.execute("SELECT relative_effort, max_hr_used FROM activities").fetchone() == (pytest.approx(60 * 2.1), None)   # zones no longer come from max HR
