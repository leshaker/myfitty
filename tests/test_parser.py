from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from myfitty.ingest.parser import FitParseError, NotAnActivity, parse_fit
from myfitty.ingest.samples import read_samples, sample_relpath, write_samples
from myfitty.metrics.tss import normalized_power

FIX = Path(__file__).parent / "fixtures"


def test_ride_with_power_and_hr():
    a = parse_fit(FIX / "ride_power_hr.fit")
    assert a.sport == "cycling" and a.sub_sport == "road"
    assert a.start_time == datetime(2026, 3, 10, 7, 0, 0, tzinfo=timezone.utc)
    assert a.serial == "111"
    assert a.elapsed_seconds == 1200 and a.moving_seconds == 1170  # 30 s pause
    assert a.distance_m == pytest.approx(5850)
    assert a.avg_hr == pytest.approx(135, abs=1) and a.max_hr == 150
    assert set(a.hr_histogram) == {120, 150}
    assert sum(a.hr_histogram.values()) == 1170  # pause seconds have no HR
    # NP computed on the 1 Hz series with the pause counted as zero power
    assert a.normalized_power == pytest.approx(normalized_power(a.samples["power"].to_numpy()))
    assert a.max_power == 250 and a.normalized_power > a.avg_power > 0


def test_hr_only_run():
    a = parse_fit(FIX / "run_hr_only.fit")
    assert a.sport == "running" and a.sub_sport == "street" and a.serial == "222"
    assert a.hr_histogram == {150: 600}
    assert a.avg_power is None and a.max_power is None and a.normalized_power is None


def test_no_sensors_stores_duration_only():
    a = parse_fit(FIX / "indoor_nosensor.fit")
    assert a.sub_sport == "indoor_cycling" and a.moving_seconds == 300
    assert a.avg_hr is None and a.max_hr is None and a.avg_power is None
    assert a.normalized_power is None and a.hr_histogram == {}


def test_missing_sport_is_unknown():
    a = parse_fit(FIX / "no_sport.fit")
    assert a.sport == "unknown" and a.sub_sport is None


def test_non_activity_and_corrupt():
    with pytest.raises(NotAnActivity):
        parse_fit(FIX / "non_activity.fit")
    with pytest.raises(FitParseError):
        parse_fit(FIX / "corrupt.fit")
    with pytest.raises(FitParseError):
        parse_fit(FIX / "does_not_exist.fit")


def test_samples_one_row_per_second_with_gap():
    a = parse_fit(FIX / "ride_power_hr.fit")
    s = a.samples
    assert list(s.columns) == ["t", "hr", "power", "speed", "lat", "lon", "altitude"]
    assert len(s) == 1200  # one per second of recorded time, pause included
    assert s["t"].is_monotonic_increasing and s["t"].diff().dropna().eq(1).all()
    assert s["power"].iloc[300:330].isna().all() and s["power"].iloc[0] == 150
    assert s["lat"].iloc[0] == pytest.approx(47.0, abs=1e-4)


def test_parquet_roundtrip_through_duckdb(tmp_path):
    ride = parse_fit(FIX / "ride_power_hr.fit")
    indoor = parse_fit(FIX / "indoor_nosensor.fit")
    r1 = sample_relpath(ride.sport, ride.start_time, ride.serial)
    r2 = sample_relpath(indoor.sport, indoor.start_time, indoor.serial)
    assert r1.startswith("sport=cycling/year=2026/") and r1.endswith(".parquet")
    write_samples(tmp_path, r1, ride.samples)
    write_samples(tmp_path, r2, indoor.samples)
    assert not list(tmp_path.rglob("*.tmp"))

    con = duckdb.connect()
    n, = con.execute("SELECT count(*) FROM read_parquet(?)", [str(tmp_path / r1)]).fetchone()
    assert n == 1200
    cols = [d[0] for d in con.execute("SELECT * FROM read_parquet(?, hive_partitioning=false)",
                                      [str(tmp_path / r1)]).description]
    assert cols == ["t", "hr", "power", "speed", "lat", "lon", "altitude"]
    # whole dataset, hive partitioned by sport and year
    by_sport = dict(con.execute(
        f"SELECT sport, count(*) FROM read_parquet('{tmp_path}/**/*.parquet', hive_partitioning=true) "
        "GROUP BY sport").fetchall())
    assert by_sport == {"cycling": 1200 + 300}
    # indoor activity has no position
    lat, = con.execute("SELECT count(lat) FROM read_parquet(?)", [str(tmp_path / r2)]).fetchone()
    assert lat == 0
    # re-writing the same key overwrites rather than adding a file
    write_samples(tmp_path, r1, ride.samples)
    assert len(list(tmp_path.rglob("*.parquet"))) == 2
    assert len(read_samples(tmp_path, r1)) == 1200
