import pytest


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Run every test in an empty folder so a developer's real ./myfitty.toml is never picked up."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MYFITTY_CONFIG", raising=False)
