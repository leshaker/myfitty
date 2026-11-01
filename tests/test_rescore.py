import time
from datetime import date, datetime, timezone

import pytest

from myfitty import db
from myfitty.config import Config
from myfitty.ingest.importer import scan
from myfitty.rescore import remove_threshold, rescore, save_threshold
from tests import fitgen
import os


@pytest.fixture
def env(tmp_path):
    cfg = Config(tmp_path / "fit", tmp_path / "t.duckdb", tmp_path / "samples")
    cfg.fit_dir.mkdir()
    for name, month in (("early.fit", 3), ("late.fit", 7)):
        p = cfg.fit_dir / name
        p.write_bytes(fitgen.ride_power_hr(start=datetime(2026, month, 10, 7, tzinfo=timezone.utc),
                                           serial=100 + month))
        os.utime(p, (time.time() - 3600,) * 2)
    with db.connect(cfg.db_path) as con:
        scan(con, cfg)
        yield con


def tss(con):
    return dict(con.execute("SELECT local_date, tss FROM activities ORDER BY local_date").fetchall())


EARLY, LATE = date(2026, 3, 10), date(2026, 7, 10)


def test_unscored_until_first_threshold_then_rescored(env):
    assert tss(env) == {EARLY: None, LATE: None}
    assert env.execute("SELECT DISTINCT unscored_reason FROM activities").fetchall() == [("no_threshold",)]
    assert save_threshold(env, "ftp", date(2026, 1, 1), 240) == 2
    s = tss(env)
    assert s[EARLY] > 0 and s[LATE] == pytest.approx(s[EARLY])


def test_new_threshold_does_not_rescore_earlier_activities(env):
    save_threshold(env, "ftp", date(2026, 1, 1), 240)
    before = tss(env)
    assert save_threshold(env, "ftp", date(2026, 6, 1), 260) == 1  # only the late activity
    after = tss(env)
    assert after[EARLY] == before[EARLY]
    assert after[LATE] == pytest.approx(before[LATE] * (240 / 260) ** 2)
    assert env.execute("SELECT ftp_used FROM activities ORDER BY local_date").fetchall() == [(240,), (260,)]


def test_correcting_old_entry_rescores_only_its_range(env):
    save_threshold(env, "ftp", date(2026, 1, 1), 240)
    save_threshold(env, "ftp", date(2026, 6, 1), 260)
    before = tss(env)
    assert save_threshold(env, "ftp", date(2026, 1, 1), 250) == 1  # early only
    after = tss(env)
    assert after[LATE] == before[LATE]
    assert after[EARLY] == pytest.approx(before[EARLY] * (240 / 250) ** 2)


def test_delete_rescores_range(env):
    save_threshold(env, "ftp", date(2026, 1, 1), 240)
    save_threshold(env, "ftp", date(2026, 6, 1), 260)
    assert remove_threshold(env, "ftp", date(2026, 6, 1)) == 1
    s = tss(env)
    assert s[LATE] == pytest.approx(s[EARLY])
    assert remove_threshold(env, "ftp", date(2026, 6, 1)) == 0  # nothing left to delete
    assert remove_threshold(env, "ftp", date(2026, 1, 1)) == 2
    assert tss(env) == {EARLY: None, LATE: None}


def test_unrelated_metric_change_leaves_scores_untouched(env):
    save_threshold(env, "ftp", date(2026, 1, 1), 240)
    assert save_threshold(env, "threshold_hr", date(2026, 1, 1), 170) == 0  # power scoring wins; same scores


def test_rescore_all_is_idempotent(env):
    save_threshold(env, "ftp", date(2026, 1, 1), 240)
    assert rescore(env) == 0


def test_running_with_power_is_scored_by_hr_on_import_and_rescore(tmp_path):
    cfg = Config(tmp_path / "fit", tmp_path / "t.duckdb", tmp_path / "samples")
    cfg.fit_dir.mkdir()
    p = cfg.fit_dir / "run.fit"
    p.write_bytes(fitgen.make_fit(start=datetime(2026, 3, 10, 7, tzinfo=timezone.utc), seconds=3600,
                                  sport="running", sub_sport="street", serial=7,
                                  power=lambda t: 300, hr=lambda t: 150))
    os.utime(p, (time.time() - 3600,) * 2)
    with db.connect(cfg.db_path) as con:
        db.set_threshold(con, "ftp", date(2026, 1, 1), 250)
        db.set_threshold(con, "threshold_hr", date(2026, 1, 1), 165)
        scan(con, cfg)
        method, ftp = con.execute("SELECT tss_method, ftp_used FROM activities").fetchone()
        assert (method, ftp) == ("hr", None)
        # an old power-based score (from before this rule) is corrected by a full rescore
        con.execute("UPDATE activities SET tss = 999, tss_method = 'power', ftp_used = 250")
        assert rescore(con) == 1
        assert con.execute("SELECT tss_method, tss < 100 FROM activities").fetchone() == ("hr", True)


def test_cli_rescore(tmp_path):
    import subprocess, sys
    with db.connect(tmp_path / "data" / "myfitty.duckdb") as con:
        con.execute("INSERT INTO activities (start_time, local_date, device_serial, sport, moving_seconds, "
                    "normalized_power, hr_histogram, tss, tss_method, ftp_used) "
                    "VALUES ('2026-03-10 07:00:00', '2026-03-10', 'x', 'running', 3600, 300, '{\"150\": 3600}', 999, 'power', 250)")
        db.set_threshold(con, "ftp", date(2026, 1, 1), 250)
        db.set_threshold(con, "threshold_hr", date(2026, 1, 1), 165)
    out = subprocess.run([sys.executable, "-m", "myfitty.cli", "rescore"], capture_output=True, text=True)
    assert out.returncode == 0 and "rescored 1" in out.stdout, out.stderr
    with db.connect(tmp_path / "data" / "myfitty.duckdb") as con:
        assert con.execute("SELECT tss_method FROM activities").fetchone() == ("hr",)
