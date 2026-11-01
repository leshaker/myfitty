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
