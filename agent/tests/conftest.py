import pytest


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))
