"""The runs: the cap, the to-do list, the failures and the finish check."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from agent.main import run_queue
from backend import runs
from backend.db import connect
from backend.main import agent_runner, app
from backend.runs import queue_runner

client = TestClient(app)

OLD_SCHEMA = """
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    in_progress INTEGER NOT NULL DEFAULT 0,
    outcome TEXT,
    payout REAL,
    reason TEXT,
    policy_section TEXT,
    paid_amount REAL,
    signed_off_by TEXT
);
CREATE TABLE records (
    kind TEXT,
    record_id TEXT,
    data TEXT,
    PRIMARY KEY (kind, record_id)
);
CREATE TABLE steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    name TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


@pytest.fixture(autouse=True)
def quiet_runners():
    app.dependency_overrides[queue_runner] = lambda: lambda run_id: None
    app.dependency_overrides[agent_runner] = lambda: lambda claim_id, thread_id: None
    yield
    app.dependency_overrides.clear()


def start_run(cap=5):
    response = client.post("/api/runs", json={"cap": cap})
    assert response.status_code == 202
    return response.json()


def items(run):
    return [(item["claim_id"], item["state"]) for item in run["items"]]


def fail(claim_id):
    client.post(f"/api/claims/{claim_id}/run")
    client.post(f"/api/claims/{claim_id}/finish", json={"note": "Error: down"})


def test_the_queue_runner_is_the_agent():
    assert queue_runner() is run_queue


def test_a_database_from_the_pilot_is_migrated(tmp_path, monkeypatch):
    path = tmp_path / "pilot.db"
    with sqlite3.connect(path) as old:
        old.executescript(OLD_SCHEMA)
        old.execute(
            "INSERT INTO claims (claim_id, data, outcome, payout)"
            " VALUES ('CLM-1001', '{}', 'approve', 420.0)"
        )
    monkeypatch.setenv("UNDERCOVER_DB", str(path))
    conn = connect()
    claim = conn.execute(
        "SELECT outcome, payout, failures FROM claims WHERE claim_id = 'CLM-1001'"
    ).fetchone()
    assert claim["outcome"] == "approve"
    assert claim["payout"] == 420.0
    assert claim["failures"] == 0
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'runs'").fetchone()


def test_a_run_takes_the_waiting_claims_up_to_the_cap():
    run = start_run(5)
    assert items(run) == [
        ("CLM-1001", "to_do"),
        ("CLM-1002", "to_do"),
        ("CLM-1003", "to_do"),
        ("CLM-1004", "to_do"),
        ("CLM-1005", "to_do"),
    ]
    assert run["cap"] == 5
    assert run["finished_at"] is None
    assert run["summary"] is None
    waiting = [
        c["claim_id"]
        for c in client.get("/api/claims").json()
        if c["status"] == "waiting"
    ]
    assert len(waiting) == 25
    assert "CLM-1006" in waiting


def test_the_current_run_is_the_last_one():
    assert client.get("/api/runs/current").json() is None
    run = start_run(2)
    assert client.get("/api/runs/current").json()["run_id"] == run["run_id"]


def test_a_second_run_is_refused_while_one_is_live(monkeypatch):
    monkeypatch.setattr(runs, "LIVE", {"a-live-run"})
    assert client.post("/api/runs", json={"cap": 5}).status_code == 409


def test_a_run_with_nothing_waiting_is_refused():
    with connect() as conn:
        conn.execute("UPDATE claims SET outcome = 'decline', payout = 0")
        conn.commit()
    response = client.post("/api/runs", json={"cap": 5})
    assert response.status_code == 409
    assert response.json()["detail"] == "No claims are waiting"


def test_a_run_needs_a_cap():
    assert client.post("/api/runs", json={"cap": 0}).status_code == 422


def test_an_interrupted_run_is_put_right():
    client.post("/api/claims/CLM-1001/run")
    with connect() as conn:
        conn.execute("INSERT INTO runs (run_id, cap) VALUES ('dead', 5)")
        conn.execute(
            "INSERT INTO run_items (run_id, claim_id, state)"
            " VALUES ('dead', 'CLM-1002', 'to_do')"
        )
        conn.commit()
    run = start_run(1)
    assert [i["claim_id"] for i in run["items"]] == ["CLM-1001"]
    claim = client.get("/api/claims/CLM-1001").json()
    assert claim["status"] == "waiting"
    assert claim["steps"][-1]["detail"] == "The run was interrupted"
    dead = client.get("/api/runs/dead").json()
    assert dead["summary"] == "The run was interrupted"
    assert dead["finished_at"] is not None


def test_an_unknown_run_is_not_found():
    assert client.get("/api/runs/nope").status_code == 404


def test_each_item_state_is_stored():
    run = start_run(2)
    for state in ("in_progress", "done", "left_for_handler", "to_do"):
        response = client.post(
            f"/api/runs/{run['run_id']}/items/CLM-1001",
            json={"state": state, "note": f"moved to {state}"},
        )
        assert response.status_code == 200
        assert response.json()["items"][0] == {
            "claim_id": "CLM-1001",
            "state": state,
            "note": f"moved to {state}",
        }


def test_a_bad_item_is_refused():
    run = start_run(2)
    path = f"/api/runs/{run['run_id']}/items/CLM-1001"
    assert client.post(path, json={"state": "nearly", "note": ""}).status_code == 422
    assert (
        client.post(
            f"/api/runs/{run['run_id']}/items/CLM-1009",
            json={"state": "done", "note": ""},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/runs/nope/items/CLM-1001", json={"state": "done", "note": ""}
        ).status_code
        == 404
    )


def test_a_run_cannot_finish_with_an_item_still_to_do():
    run = start_run(2)
    response = client.post(
        f"/api/runs/{run['run_id']}/finish", json={"summary": "done"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Still to work: CLM-1001, CLM-1002"


def test_a_run_cannot_finish_on_a_claim_with_no_decision():
    run = start_run(1)
    client.post(
        f"/api/runs/{run['run_id']}/items/CLM-1001",
        json={"state": "done", "note": "approved"},
    )
    response = client.post(
        f"/api/runs/{run['run_id']}/finish", json={"summary": "done"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Still to work: CLM-1001"


def test_a_run_finishes_with_a_summary():
    run = start_run(2)
    for claim_id in ("CLM-1001", "CLM-1002"):
        client.post(f"/api/claims/{claim_id}/run")
        client.post(
            f"/api/claims/{claim_id}/decision",
            json={
                "outcome": "decline",
                "payout": 0,
                "reason": "Not covered.",
                "policy_section": "9. General exclusions",
            },
        )
        client.post(f"/api/claims/{claim_id}/finish", json={"note": "Declined."})
        client.post(
            f"/api/runs/{run['run_id']}/items/{claim_id}",
            json={"state": "done", "note": "declined"},
        )
    finished = client.post(
        f"/api/runs/{run['run_id']}/finish", json={"summary": "Two claims declined."}
    ).json()
    assert finished["summary"] == "Two claims declined."
    assert finished["finished_at"] is not None
    assert (
        client.post(
            f"/api/runs/{run['run_id']}/finish", json={"summary": "again"}
        ).status_code
        == 409
    )


def test_a_claim_left_for_a_handler_does_not_block_the_run():
    run = start_run(1)
    client.post(
        f"/api/runs/{run['run_id']}/items/CLM-1001",
        json={"state": "left_for_handler", "note": "failed twice"},
    )
    assert (
        client.post(
            f"/api/runs/{run['run_id']}/finish", json={"summary": "Left for a handler."}
        ).status_code
        == 200
    )


def test_a_failed_claim_counts_and_is_left_alone_after_two():
    fail("CLM-1001")
    claims = {c["claim_id"]: c for c in client.get("/api/claims").json()}
    assert claims["CLM-1001"]["status"] == "waiting"
    assert claims["CLM-1001"]["failures"] == 1
    fail("CLM-1001")
    assert client.get("/api/claims/CLM-1001").json()["failures"] == 2
    run = start_run(3)
    assert [i["claim_id"] for i in run["items"]] == ["CLM-1002", "CLM-1003", "CLM-1004"]


def test_a_claim_that_is_decided_is_not_a_failure():
    client.post("/api/claims/CLM-1001/run")
    client.post(
        "/api/claims/CLM-1001/decision",
        json={
            "outcome": "approve",
            "payout": 420.0,
            "reason": "Covered.",
            "policy_section": "3. Trip Delay",
        },
    )
    client.post("/api/claims/CLM-1001/finish", json={"note": "Approved."})
    assert client.get("/api/claims/CLM-1001").json()["failures"] == 0
