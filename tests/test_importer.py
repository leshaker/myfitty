import hashlib
import os
import shutil
import time
from datetime import date
from pathlib import Path

import pytest

from myfitty import db
from myfitty.config import Config
from myfitty.ingest import importer
from myfitty.ingest.importer import scan
from myfitty.ingest.samples import read_samples
from tests import fitgen

FIX = Path(__file__).parent / "fixtures"
OLD = time.time() - 3600  # make files look settled


@pytest.fixture
def env(tmp_path):
    cfg = Config(fit_dir=tmp_path / "fit", db_path=tmp_path / "t.duckdb", samples_dir=tmp_path / "samples")
    cfg.fit_dir.mkdir()
    with db.connect(cfg.db_path) as con:
        yield cfg, con


def put(cfg, name, data=None, src=None, age=3600):
    p = cfg.fit_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if data is not None else (FIX / src).read_bytes())
    t = time.time() - age
    os.utime(p, (t, t))
    return p


def count(con):
    return con.execute("SELECT count(*) FROM activities").fetchone()[0]


def test_initial_scan_imports_all_valid_files(env):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit")
    put(cfg, "sub/b.fit", src="run_hr_only.fit")
    put(cfg, "c.FIT", src="indoor_nosensor.fit")
    r = scan(con, cfg)
    assert r.imported == 3 and not r.failures and count(con) == 3


def test_missing_folder(env):
    cfg, con = env
    r = scan(con, Config(cfg.fit_dir / "nope", cfg.db_path, cfg.samples_dir))
    assert r.folder_missing and r.imported == 0


def test_stored_summary_and_samples(env):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit")
    scan(con, cfg)
    row = con.execute("SELECT sport, sub_sport, device_serial, moving_seconds, normalized_power, hr_histogram, "
                      "sample_path, start_time FROM activities").fetchone()
    assert row[:4] == ("cycling", "road", "111", 1170)
    assert row[4] > 0 and row[5] is not None
    assert len(read_samples(cfg.samples_dir, row[6])) == 1200
    assert str(row[7]) == "2026-03-10 07:00:00"


def test_no_sensor_activity_is_stored_unscored(env):
    cfg, con = env
    put(cfg, "i.fit", src="indoor_nosensor.fit")
    scan(con, cfg)
    row = con.execute("SELECT avg_hr, normalized_power, hr_histogram, tss, unscored_reason, moving_seconds "
                      "FROM activities").fetchone()
    assert row == (None, None, None, None, "no_data", 300)


def test_same_file_twice_is_duplicate(env):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit")
    scan(con, cfg)
    con.execute("DELETE FROM source_files")  # force a re-read of the same path
    r = scan(con, cfg)
    assert r.imported == 0 and r.duplicates == 1 and count(con) == 1


def test_renamed_copy_is_duplicate(env):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit")
    put(cfg, "copy/other-name.fit", src="ride_power_hr.fit")
    r = scan(con, cfg)
    assert r.imported == 1 and r.duplicates == 1


def test_same_start_and_serial_different_content_is_duplicate(env):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit")
    put(cfg, "b.fit", data=fitgen.ride_power_hr(power=lambda t: 200))  # same start + serial
    r = scan(con, cfg)
    assert r.imported == 1 and r.duplicates == 1


def test_missing_serial_falls_back_to_file_hash(env):
    cfg, con = env
    data = fitgen.run_hr_only(serial=None)
    put(cfg, "a.fit", data=data)
    put(cfg, "b.fit", data=data)  # identical bytes -> same hash -> duplicate
    put(cfg, "c.fit", data=fitgen.run_hr_only(serial=None, hr=lambda t: 140))  # different bytes -> distinct
    r = scan(con, cfg)
    assert r.imported == 2 and r.duplicates == 1
    serials = {s for (s,) in con.execute("SELECT device_serial FROM activities").fetchall()}
    assert "sha256:" + hashlib.sha256(data).hexdigest() in serials


def test_corrupt_file_in_batch_does_not_abort(env):
    cfg, con = env
    for i in range(9):
        put(cfg, f"ok{i}.fit", data=fitgen.run_hr_only(start=fitgen.RUN_START.replace(day=1 + i), serial=900 + i))
    put(cfg, "bad.fit", src="corrupt.fit")
    r = scan(con, cfg)
    assert r.imported == 9 and len(r.failures) == 1
    name, reason = r.failures[0]
    assert name == "bad.fit" and "decode" in reason
    assert con.execute("SELECT count(*) FROM ingest_failures").fetchone()[0] == 1


def test_non_activity_is_skipped_with_reason(env):
    cfg, con = env
    put(cfg, "settings.fit", src="non_activity.fit")
    r = scan(con, cfg)
    assert r.imported == 0 and r.failures == [("settings.fit", "not an activity (no session message)")]


def test_failed_file_retried_after_fix(env):
    cfg, con = env
    p = put(cfg, "a.fit", src="corrupt.fit")
    assert len(scan(con, cfg).failures) == 1
    r = scan(con, cfg)  # unchanged failure: not retried, not re-reported
    assert r.unchanged == 1 and not r.failures
    put(cfg, "a.fit", src="ride_power_hr.fit")  # replaced with a valid file
    r = scan(con, cfg)
    assert r.imported == 1 and not r.failures
    assert con.execute("SELECT count(*) FROM ingest_failures").fetchone()[0] == 0


def test_source_folder_untouched(env):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit")
    put(cfg, "bad.fit", src="corrupt.fit")
    before = {p: (p.read_bytes(), p.stat().st_mtime) for p in cfg.fit_dir.rglob("*") if p.is_file()}
    scan(con, cfg)
    scan(con, cfg)
    after = {p: (p.read_bytes(), p.stat().st_mtime) for p in cfg.fit_dir.rglob("*") if p.is_file()}
    assert before == after and not list(cfg.fit_dir.glob("*.tmp"))


def test_scores_use_thresholds_in_effect(env):
    cfg, con = env
    db.set_threshold(con, "ftp", date(2026, 1, 1), 200)
    db.set_threshold(con, "max_hr", date(2026, 1, 1), 190)
    put(cfg, "a.fit", src="ride_power_hr.fit")
    scan(con, cfg)
    tss, method, ftp, trimp = con.execute("SELECT tss, tss_method, ftp_used, trimp FROM activities").fetchone()
    assert method == "power" and ftp == 200 and tss > 0 and trimp > 0


# --- 4.6: on-demand scanning ---
def test_unchanged_file_is_not_reparsed(env, monkeypatch):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit")
    scan(con, cfg)
    calls = []
    real = importer.parse_fit
    monkeypatch.setattr(importer, "parse_fit", lambda p: calls.append(p) or real(p))
    r = scan(con, cfg)
    assert r.unchanged == 1 and r.imported == 0 and calls == []


def test_recently_modified_file_is_deferred(env):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit", age=0.2)
    r = scan(con, cfg)
    assert r.deferred == 1 and r.imported == 0 and count(con) == 0
    assert con.execute("SELECT count(*) FROM source_files").fetchone()[0] == 0
    r = scan(con, cfg, now=time.time() + 5)  # later, once it has settled
    assert r.imported == 1 and r.deferred == 0


def test_new_file_picked_up_by_later_scan(env):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit")
    scan(con, cfg)
    put(cfg, "b.fit", src="run_hr_only.fit")
    r = scan(con, cfg)
    assert r.imported == 1 and r.unchanged == 1 and count(con) == 2


def test_interrupted_import_leaves_one_set_of_samples(env, monkeypatch):
    cfg, con = env
    put(cfg, "a.fit", src="ride_power_hr.fit")
    orig = importer.write_samples

    def write_then_crash(*a, **k):
        orig(*a, **k)
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(importer, "write_samples", write_then_crash)
    r = scan(con, cfg)
    assert r.imported == 0 and len(r.failures) == 1 and count(con) == 0
    assert len(list(cfg.samples_dir.rglob("*.parquet"))) == 1
    monkeypatch.setattr(importer, "write_samples", orig)
    put(cfg, "a.fit", src="ride_power_hr.fit")  # touched again (e.g. copied again): mtime changes
    r = scan(con, cfg, now=time.time() + 5)
    assert r.imported == 1 and count(con) == 1
    assert len(list(cfg.samples_dir.rglob("*.parquet"))) == 1


def test_cli_runs(tmp_path):
    import subprocess, sys
    fit = tmp_path / "fit"
    fit.mkdir()
    put(Config(fit, tmp_path / "d.duckdb", tmp_path / "s"), "a.fit", src="ride_power_hr.fit")
    env = {**os.environ, "MYFITTY_FIT_DIR": str(fit), "MYFITTY_DB": str(tmp_path / "d.duckdb"),
           "MYFITTY_SAMPLES_DIR": str(tmp_path / "s")}
    out = subprocess.run([sys.executable, "-m", "myfitty.ingest"], env=env, capture_output=True, text=True)
    assert out.returncode == 0 and "1 imported" in out.stdout
    out = subprocess.run([sys.executable, "-m", "myfitty.ingest"], env=env, capture_output=True, text=True)
    assert "1 unchanged" in out.stdout


def test_myfitty_entrypoint(tmp_path):
    import subprocess, sys
    from myfitty import cli
    assert cli.main([]) == 2 and cli.main(["bogus"]) == 2 and cli.main(["--help"]) == 0
    fit = tmp_path / "fit"
    fit.mkdir()
    put(Config(fit, tmp_path / "d.duckdb", tmp_path / "s"), "a.fit", src="ride_power_hr.fit")
    env = {**os.environ, "MYFITTY_FIT_DIR": str(fit), "MYFITTY_DB": str(tmp_path / "d.duckdb"),
           "MYFITTY_SAMPLES_DIR": str(tmp_path / "s")}
    out = subprocess.run([sys.executable, "-m", "myfitty.cli", "ingest"], env=env, capture_output=True, text=True)
    assert out.returncode == 0 and "1 imported" in out.stdout
