import json

import pytest
from fastapi.testclient import TestClient

from agent.harness import run_claim
from backend.db import connect
from backend.main import agent_runner, app

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_agent():
    app.dependency_overrides[agent_runner] = lambda: lambda claim_id, thread_id: None
    yield
    app.dependency_overrides.clear()


def start(claim_id):
    response = client.post(f"/api/claims/{claim_id}/run")
    assert response.status_code == 202
    return response.json()


def decide(claim_id, outcome, payout, start_first=True):
    if start_first:
        start(claim_id)
    return client.post(
        f"/api/claims/{claim_id}/decision",
        json={
            "outcome": outcome,
            "payout": payout,
            "reason": "Covered by the wording.",
            "policy_section": "3. Trip Delay",
        },
    )


def pay(claim_id, amount):
    return client.post(f"/api/claims/{claim_id}/payment", json={"amount": amount})


def sign_off(claim_id, handler_id):
    return client.post(
        f"/api/claims/{claim_id}/sign-off", json={"handler_id": handler_id}
    )


def get(claim_id):
    return client.get(f"/api/claims/{claim_id}").json()


def test_run_starts_and_finish_ends():
    claim = start("CLM-1001")
    assert claim["status"] == "in_progress"
    assert claim["steps"][0]["name"] == "started"
    assert client.post("/api/claims/CLM-1001/run").status_code == 409
    response = client.post("/api/claims/CLM-1001/finish", json={"note": "No decision"})
    assert response.json()["status"] == "waiting"
    assert response.json()["steps"][-1] == {
        "at": response.json()["steps"][-1]["at"],
        "name": "finished",
        "detail": "No decision",
    }


def test_steps_only_while_in_progress():
    step = {"name": "get_claim", "detail": "CLM-1001"}
    assert client.post("/api/claims/CLM-1001/steps", json=step).status_code == 409
    start("CLM-1001")
    assert client.post("/api/claims/CLM-1001/steps", json=step).status_code == 200
    assert get("CLM-1001")["steps"][-1]["name"] == "get_claim"
    finish = client.post("/api/claims/CLM-1001/finish", json={"note": "done"})
    assert finish.status_code == 200
    assert (
        client.post("/api/claims/CLM-1001/finish", json={"note": "x"}).status_code
        == 409
    )


def test_pay_under_the_limit():
    assert decide("CLM-1001", "approve", 420.0).status_code == 200
    response = pay("CLM-1001", 420.0)
    assert response.status_code == 200
    client.post("/api/claims/CLM-1001/finish", json={"note": "done"})
    claim = get("CLM-1001")
    assert claim["status"] == "decided"
    assert claim["payment"] == {"amount": 420.0, "signed_off_by": None}
    assert pay("CLM-1001", 420.0).status_code == 409


def test_over_the_limit_waits_for_sign_off():
    decide("CLM-1002", "approve", 1250.0)
    client.post("/api/claims/CLM-1002/finish", json={"note": "done"})
    assert get("CLM-1002")["status"] == "awaiting_signoff"
    response = pay("CLM-1002", 1250.0)
    assert response.status_code == 409
    assert "sign-off" in response.json()["detail"]
    assert get("CLM-1002")["payment"] is None
    assert sign_off("CLM-1002", "HND-01").status_code == 200
    claim = get("CLM-1002")
    assert claim["status"] == "decided"
    assert claim["payment"] == {"amount": 1250.0, "signed_off_by": "HND-01"}
    assert pay("CLM-1002", 1250.0).status_code == 409


def test_payment_blocked_even_during_the_run():
    decide("CLM-1002", "approve", 1250.0)
    assert pay("CLM-1002", 1250.0).status_code == 409
    assert get("CLM-1002")["payment"] is None


def test_sign_off_needs_a_handler_who_may_approve():
    decide("CLM-1002", "approve", 1250.0)
    client.post("/api/claims/CLM-1002/finish", json={"note": "done"})
    with connect() as conn:
        trainee = {
            "handler_id": "HND-09",
            "name": "Trainee",
            "can_approve_over_limit": False,
        }
        conn.execute(
            "INSERT INTO records VALUES ('handler', 'HND-09', ?)",
            (json.dumps(trainee),),
        )
    assert sign_off("CLM-1002", "HND-09").status_code == 403
    assert sign_off("CLM-1002", "HND-99").status_code == 404
    assert get("CLM-1002")["status"] == "awaiting_signoff"


def test_sign_off_only_when_awaiting():
    decide("CLM-1001", "approve", 420.0)
    client.post("/api/claims/CLM-1001/finish", json={"note": "done"})
    assert sign_off("CLM-1001", "HND-01").status_code == 409
    assert sign_off("CLM-1003", "HND-01").status_code == 409


@pytest.mark.parametrize(
    ("claim_id", "outcome", "payout", "amount"),
    [
        ("CLM-1001", "approve", 420.0, 400.0),
        ("CLM-1001", "decline", 0, 0),
        ("CLM-1001", "refer", 0, 0),
    ],
)
def test_bad_payments(claim_id, outcome, payout, amount):
    decide(claim_id, outcome, payout)
    assert pay(claim_id, amount).status_code == 409
    assert get(claim_id)["payment"] is None


def test_pay_with_no_decision():
    assert pay("CLM-1001", 420.0).status_code == 409


@pytest.mark.parametrize(
    ("outcome", "payout"), [("pay", 10.0), ("approve", 0), ("decline", 50.0)]
)
def test_invalid_decisions(outcome, payout):
    assert decide("CLM-1001", outcome, payout).status_code == 422


def test_decision_only_once_and_only_in_progress():
    assert decide("CLM-1001", "refer", 0, start_first=False).status_code == 409
    assert decide("CLM-1001", "refer", 0).status_code == 200
    assert decide("CLM-1001", "refer", 0, start_first=False).status_code == 409
    client.post("/api/claims/CLM-1001/finish", json={"note": "done"})
    claim = get("CLM-1001")
    assert claim["status"] == "decided"
    assert claim["decision"] == {
        "outcome": "refer",
        "payout": 0.0,
        "reason": "Covered by the wording.",
        "policy_section": "3. Trip Delay",
    }


def test_run_hands_the_claim_to_the_runner():
    calls = []
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: calls.append((c, t))
    start("CLM-1005")
    assert calls[0][0] == "CLM-1005"
    assert calls[0][1]


def test_agent_runner_is_the_agent():
    assert agent_runner() is run_claim


def test_the_queue_shows_each_decision():
    decide("CLM-1002", "approve", 1250.0)
    client.post("/api/claims/CLM-1002/finish", json={"note": "done"})
    claims = {c["claim_id"]: c for c in client.get("/api/claims").json()}
    assert claims["CLM-1002"]["outcome"] == "approve"
    assert claims["CLM-1002"]["payout"] == 1250.0
    assert claims["CLM-1001"]["outcome"] is None
