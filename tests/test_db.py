from datetime import date

import pytest

from myfitty import db


def _insert(con, serial="A", hour=8):
    con.execute(
        "INSERT INTO activities (start_time, local_date, device_serial, sport) "
        "VALUES (?, ?, ?, 'cycling')", [f"2026-01-01 {hour:02d}:00:00", date(2026, 1, 1), serial])


def test_schema_idempotent_and_persistent(tmp_path):
    path = tmp_path / "x.duckdb"
    with db.connect(path) as con:
        _insert(con)
    with db.connect(path) as con:  # reopen: schema re-applied, data kept
        assert con.execute("SELECT count(*) FROM activities").fetchone()[0] == 1
        for t in ("activities", "threshold_entries", "ingest_failures", "source_files"):
            con.execute(f"SELECT * FROM {t} LIMIT 0")


def test_second_connection_after_first_closes(tmp_path):
    path = tmp_path / "x.duckdb"
    with db.connect(path):
        pass
    with db.connect(path) as con:
        assert con.execute("SELECT 1").fetchone() == (1,)


def test_lock_retry_waits_for_other_process(tmp_path):
    import subprocess, sys, time
    path = tmp_path / "x.duckdb"
    with db.connect(path):
        pass
    holder = subprocess.Popen([sys.executable, "-c",
        "import duckdb, sys, time; c = duckdb.connect(sys.argv[1]); print('ready', flush=True); time.sleep(1.0)",
        str(path)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ready"
        t0 = time.time()
        with db.connect(path) as con:  # blocked by the other process, then succeeds
            assert con.execute("SELECT 1").fetchone() == (1,)
        assert time.time() - t0 >= 0.5
    finally:
        holder.wait()


def test_unique_start_and_serial(tmp_path):
    import duckdb
    with db.connect(tmp_path / "x.duckdb") as con:
        _insert(con)
        with pytest.raises(duckdb.ConstraintException):
            _insert(con)
        _insert(con, serial="B")


def test_update_on_unique_table_works(tmp_path):
    with db.connect(tmp_path / "x.duckdb") as con:
        _insert(con)
        con.execute("UPDATE activities SET tss = 55, tss_method = 'power'")
        assert con.execute("SELECT tss FROM activities").fetchone()[0] == 55


@pytest.fixture
def con(tmp_path):
    with db.connect(tmp_path / "t.duckdb") as c:
        yield c


def test_between_entries(con):
    db.set_threshold(con, "ftp", date(2026, 1, 1), 240)
    db.set_threshold(con, "ftp", date(2026, 6, 1), 260)
    assert db.threshold_on(con, "ftp", date(2026, 3, 15)) == 240
    assert db.threshold_on(con, "ftp", date(2026, 6, 1)) == 260
    assert db.threshold_on(con, "ftp", date(2027, 1, 1)) == 260
    assert [(e[1], e[2]) for e in db.list_thresholds(con, "ftp")] == [
        (date(2026, 1, 1), 240), (date(2026, 6, 1), 260)]


def test_before_first_uses_earliest(con):
    db.set_threshold(con, "ftp", date(2026, 1, 1), 240)
    assert db.threshold_on(con, "ftp", date(2025, 11, 1)) == 240


def test_none_configured(con):
    assert db.threshold_on(con, "ftp", date(2026, 1, 1)) is None
    assert db.thresholds_on(con, date(2026, 1, 1)) == {"ftp": None, "threshold_hr": None, "max_hr": None}


def test_same_date_replaces(con):
    db.set_threshold(con, "ftp", date(2026, 1, 1), 240)
    db.set_threshold(con, "ftp", date(2026, 1, 1), 250)
    assert len(db.list_thresholds(con, "ftp")) == 1
    assert db.threshold_on(con, "ftp", date(2026, 2, 1)) == 250


def test_metrics_have_independent_history(con):
    db.set_threshold(con, "ftp", date(2026, 1, 1), 240)
    db.set_threshold(con, "max_hr", date(2026, 3, 1), 190)
    assert db.threshold_on(con, "max_hr", date(2026, 2, 1)) == 190  # before-first fallback
    assert db.threshold_on(con, "ftp", date(2026, 2, 1)) == 240


@pytest.mark.parametrize("bad", [0, -5, None, "x", True])
def test_invalid_values_rejected(con, bad):
    with pytest.raises(ValueError):
        db.set_threshold(con, "ftp", date(2026, 1, 1), bad)
    assert db.list_thresholds(con) == []


def test_unknown_metric_rejected(con):
    with pytest.raises(ValueError):
        db.set_threshold(con, "vo2max", date(2026, 1, 1), 50)


def test_threshold_hr_above_max_hr_rejected(con):
    db.set_threshold(con, "max_hr", date(2026, 1, 1), 190)
    with pytest.raises(ValueError):
        db.set_threshold(con, "threshold_hr", date(2026, 1, 1), 195)
    db.set_threshold(con, "threshold_hr", date(2026, 1, 1), 170)
    with pytest.raises(ValueError):  # lowering max below threshold
        db.set_threshold(con, "max_hr", date(2026, 2, 1), 165)


def test_affected_ranges(con):
    assert db.set_threshold(con, "ftp", date(2026, 1, 1), 240) == (None, None)
    assert db.set_threshold(con, "ftp", date(2026, 6, 1), 260) == (date(2026, 6, 1), None)
    # editing the early entry affects everything before the next entry, including pre-first dates
    assert db.set_threshold(con, "ftp", date(2026, 1, 1), 250) == (None, date(2026, 6, 1))
    assert db.set_threshold(con, "ftp", date(2026, 3, 1), 255) == (date(2026, 3, 1), date(2026, 6, 1))


def test_delete(con):
    db.set_threshold(con, "ftp", date(2026, 1, 1), 240)
    db.set_threshold(con, "ftp", date(2026, 6, 1), 260)
    assert db.delete_threshold(con, "ftp", date(2026, 6, 1)) == (date(2026, 6, 1), None)
    assert db.threshold_on(con, "ftp", date(2026, 7, 1)) == 240
    assert db.delete_threshold(con, "ftp", date(2026, 6, 1)) is None  # already gone
    assert db.delete_threshold(con, "ftp", date(2026, 1, 1)) == (None, None)
    assert db.list_thresholds(con) == []
