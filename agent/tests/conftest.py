import pytest
from fastapi.testclient import TestClient

from agent import api
from backend.main import app


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))


@pytest.fixture(autouse=True)
def in_process(monkeypatch):
    """Point the agent at the backend in this process."""
    monkeypatch.setattr(api, "client", lambda: TestClient(app))
    yield
    app.dependency_overrides.clear()
