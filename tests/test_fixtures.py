from pathlib import Path

import fitdecode
import pytest

from tests import fitgen

FIX = Path(__file__).parent / "fixtures"


def _messages(path):
    with fitdecode.FitReader(str(path)) as r:
        return [f.name for f in r if isinstance(f, fitdecode.FitDataMessage)]


@pytest.mark.parametrize("name", ["ride_power_hr", "run_hr_only", "indoor_nosensor", "no_sport"])
def test_activity_fixtures_load(name):
    names = _messages(FIX / f"{name}.fit")
    assert names[0] == "file_id" and "record" in names and names[-1] == "session"


def test_non_activity_fixture_has_no_session():
    assert _messages(FIX / "non_activity.fit") == ["file_id"]


def test_corrupt_fixture_fails_to_decode():
    with pytest.raises(fitdecode.FitError):
        _messages(FIX / "corrupt.fit")


def test_committed_fixtures_match_generator():
    for name, fn in fitgen.FIXTURES.items():
        assert (FIX / name).read_bytes() == fn(), f"{name} is stale; run python -m tests.fitgen"
