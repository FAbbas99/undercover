import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import main
from backend.main import agent_runner, app

client = TestClient(app)
prompts = []


class StubModel(GenericFakeChatModel):
    """A chat model that gives scripted replies in place of a real model."""

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        prompts.append(messages[0].content)
        return super()._generate(messages, *args, **kwargs)


class BrokenModel(StubModel):
    """A chat model that fails, as a model that is down would."""

    def _generate(self, messages, *args, **kwargs):
        raise RuntimeError("model unavailable")


def scripted(*calls, final="Done."):
    replies = [
        AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(i)}])
        for i, (name, args) in enumerate(calls)
    ]
    return StubModel(messages=iter([*replies, AIMessage(content=final)]))


def decision(claim_id, outcome, payout):
    return (
        "record_decision",
        {
            "claim_id": claim_id,
            "outcome": outcome,
            "payout": payout,
            "reason": "Covered under the plan.",
            "policy_section": "3. Trip Delay",
        },
    )


@pytest.fixture(autouse=True)
def in_process(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    yield
    app.dependency_overrides.clear()


def run_with(claim_id, llm):
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: main.run(c, t, llm)
    assert client.post(f"/api/claims/{claim_id}/run").status_code == 202
    return client.get(f"/api/claims/{claim_id}").json()


def step_names(claim):
    return [step["name"] for step in claim["steps"]]


def test_approve_and_pay():
    claim = run_with(
        "CLM-1001",
        scripted(
            ("get_claim", {"claim_id": "CLM-1001"}),
            ("get_policy_wording", {}),
            decision("CLM-1001", "approve", 420.0),
            ("pay_claim", {"claim_id": "CLM-1001", "amount": 420.0}),
            final="Approved and paid $420.00.",
        ),
    )
    assert claim["status"] == "decided"
    assert claim["decision"]["outcome"] == "approve"
    assert claim["payment"] == {"amount": 420.0, "signed_off_by": None}
    assert step_names(claim) == [
        "started",
        "get_claim",
        "get_policy_wording",
        "record_decision",
        "pay_claim",
        "finished",
    ]
    assert claim["steps"][-1]["detail"] == "Approved and paid $420.00."


def test_over_the_limit_payment_is_refused():
    claim = run_with(
        "CLM-1002",
        scripted(
            decision("CLM-1002", "approve", 1250.0),
            ("pay_claim", {"claim_id": "CLM-1002", "amount": 1250.0}),
        ),
    )
    assert claim["status"] == "awaiting_signoff"
    assert claim["payment"] is None
    assert "pay_claim" in step_names(claim)


def test_pay_tool_returns_the_refusal():
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: None
    client.post("/api/claims/CLM-1002/run")
    main.record_decision.invoke(decision("CLM-1002", "approve", 1250.0)[1])
    reply = main.pay_claim.invoke({"claim_id": "CLM-1002", "amount": 1250.0})
    assert reply.startswith("Refused: A payout over 1,000.00 waits")


@pytest.mark.parametrize("outcome", ["decline", "refer"])
def test_decline_and_refer(outcome):
    claim = run_with("CLM-1003", scripted(decision("CLM-1003", outcome, 0)))
    assert claim["status"] == "decided"
    assert claim["decision"] == {
        "outcome": outcome,
        "payout": 0.0,
        "reason": "Covered under the plan.",
        "policy_section": "3. Trip Delay",
    }
    assert claim["payment"] is None


def test_a_failing_model_leaves_the_claim_waiting():
    claim = run_with("CLM-1004", BrokenModel(messages=iter([])))
    assert claim["status"] == "waiting"
    assert claim["steps"][-1]["detail"] == "Error: model unavailable"


def test_a_missing_key_leaves_the_claim_waiting(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    app.dependency_overrides[agent_runner] = lambda: main.run
    client.post("/api/claims/CLM-1004/run")
    claim = client.get("/api/claims/CLM-1004").json()
    assert claim["status"] == "waiting"
    assert "OPENROUTER_API_KEY" in claim["steps"][-1]["detail"]


def test_the_agent_uses_the_served_instructions():
    prompts.clear()
    run_with("CLM-1005", scripted())
    assert prompts[0] == client.get("/api/instructions").json()["text"]


def test_run_twice_is_refused():
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: None
    assert client.post("/api/claims/CLM-1006/run").status_code == 202
    assert client.post("/api/claims/CLM-1006/run").status_code == 409


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert main.model().model_name == "openai/gpt-6-luna"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert main.model().model_name == "openrouter/free"
