"""The claim worker: its tools, its decisions, its failures and its timeout."""

import time

import pytest
from fastapi.testclient import TestClient
from langchain.tools import ToolRuntime
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import api, harness, tools
from agent.harness import run_claim
from agent.tests.e2e_server import ScriptedModel
from agent.tools import ClaimContext
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


class SlowModel(StubModel):
    """A chat model that takes longer over a claim than a worker is given."""

    def _generate(self, messages, *args, **kwargs):
        time.sleep(0.5)
        return super()._generate(messages, *args, **kwargs)


def scripted(*calls, final="Done."):
    replies = [
        AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(i)}])
        for i, (name, args) in enumerate(calls)
    ]
    return StubModel(messages=iter([*replies, AIMessage(content=final)]))


def decision(outcome, payout):
    return (
        "record_decision",
        {
            "outcome": outcome,
            "payout": payout,
            "reason": "Covered under the plan.",
            "policy_section": "3. Trip Delay",
        },
    )


def call_tool(a_tool, *args):
    """Call a tool's function directly, as the agent does with a runtime."""
    return a_tool.func(*args)


def runtime(claim_id="CLM-1001"):
    """A tool's runtime, as the agent gives it one."""
    return ToolRuntime(
        state={},
        context=ClaimContext(claim_id=claim_id),
        config={},
        stream_writer=lambda _: None,
        tool_call_id="1",
        store=None,
    )


def run_with(claim_id, llm):
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: run_claim(c, t, llm)
    assert client.post(f"/api/claims/{claim_id}/run").status_code == 202
    return client.get(f"/api/claims/{claim_id}").json()


def step_names(claim):
    return [step["name"] for step in claim["steps"]]


def test_approve_and_pay():
    claim = run_with(
        "CLM-1001",
        scripted(
            ("get_claim", {}),
            ("get_wording_section", {"section": "3"}),
            decision("approve", 420.0),
            ("pay_claim", {"amount": 420.0}),
            final="Approved and paid $420.00.",
        ),
    )
    assert claim["status"] == "decided"
    assert claim["decision"]["outcome"] == "approve"
    assert claim["payment"] == {"amount": 420.0, "signed_off_by": None}
    assert step_names(claim) == [
        "started",
        "get_claim",
        "read_wording",
        "record_decision",
        "pay_claim",
        "finished",
    ]
    assert claim["steps"][-1]["detail"] == "Approved and paid $420.00."


def test_the_claim_page_shows_what_was_read():
    claim = run_with(
        "CLM-1001",
        scripted(
            ("get_wording_section", {"section": "5"}),
            ("get_manual_section", {"section": "9"}),
            decision("decline", 0),
        ),
    )
    assert [(step["name"], step["detail"]) for step in claim["steps"]] == [
        ("started", "The agent started work on the claim"),
        ("read_wording", "5. Baggage and Personal Effects"),
        ("read_manual", "9. Repeat claims"),
        ("record_decision", "decline $0.00"),
        ("finished", "Done."),
    ]


def test_no_tool_hands_over_a_whole_document():
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: None
    client.post("/api/claims/CLM-1001/run")
    wording = call_tool(tools.get_wording_section, runtime(), "5")
    manual = call_tool(tools.get_manual_section, runtime(), "5")
    assert wording.startswith("## 5. Baggage and Personal Effects")
    assert len(wording) < 1500
    assert manual.startswith("## 5. Documents and document requests")
    assert "## 9. Repeat claims" not in manual


def test_over_the_limit_payment_is_refused():
    claim = run_with(
        "CLM-1002",
        scripted(
            decision("approve", 1250.0),
            ("pay_claim", {"amount": 1250.0}),
        ),
    )
    assert claim["status"] == "awaiting_signoff"
    assert claim["payment"] is None
    assert "pay_claim" not in step_names(claim)


def test_the_pay_tool_answers_the_model_with_the_refusal():
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: None
    client.post("/api/claims/CLM-1002/run")
    api.record_decision("CLM-1002", "approve", 1250.0, "Covered.", "3. Trip Delay")
    reply = call_tool(tools.pay_claim, runtime("CLM-1002"), 1250.0)
    assert reply.startswith("Refused: A payout over 1,000.00 waits")


def test_a_decision_is_only_recorded_once():
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: None
    client.post("/api/claims/CLM-1001/run")
    first = call_tool(
        tools.record_decision, runtime(), "refer", 0, "Needs a look.", "8. Add-ons"
    )
    again = call_tool(
        tools.record_decision, runtime(), "approve", 420.0, "Covered.", "3. Trip Delay"
    )
    assert first == "refer recorded"
    assert again.startswith("Refused: CLM-1001 already has a decision")


@pytest.mark.parametrize("outcome", ["decline", "refer"])
def test_decline_and_refer(outcome):
    claim = run_with("CLM-1003", scripted(decision(outcome, 0)))
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
    assert claim["failures"] == 1


def test_a_slow_model_is_cut_off(monkeypatch):
    monkeypatch.setattr(harness, "CLAIM_TIMEOUT_SECONDS", 0.05)
    claim = run_with("CLM-1005", SlowModel(messages=iter([])))
    assert claim["status"] == "waiting"
    assert claim["steps"][-1]["detail"] == "Timed out after 0.05 seconds"
    assert claim["failures"] == 1


def test_a_missing_key_leaves_the_claim_waiting(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    app.dependency_overrides[agent_runner] = lambda: run_claim
    client.post("/api/claims/CLM-1004/run")
    claim = client.get("/api/claims/CLM-1004").json()
    assert claim["status"] == "waiting"
    assert "OPENROUTER_API_KEY" in claim["steps"][-1]["detail"]


def test_the_agent_uses_the_served_instructions():
    prompts.clear()
    run_with("CLM-1005", scripted())
    assert prompts[0] == client.get("/api/instructions/claim").json()["text"]


def test_run_twice_is_refused():
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: None
    assert client.post("/api/claims/CLM-1006/run").status_code == 202
    assert client.post("/api/claims/CLM-1006/run").status_code == 409


def test_model_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    assert harness.model().model_name == "deepseek/deepseek-v4.1-flash"
    assert harness.model().reasoning_effort == "low"
    monkeypatch.setenv("MODEL_NAME", "openrouter/free")
    assert harness.model().model_name == "openrouter/free"
    assert harness.model().reasoning_effort is None


def test_the_e2e_scripted_model():
    paid = run_with("CLM-1001", ScriptedModel(step_seconds=0))
    assert paid["status"] == "decided"
    assert paid["payment"] == {"amount": 420.0, "signed_off_by": None}
    held = run_with("CLM-1002", ScriptedModel(step_seconds=0))
    assert held["status"] == "awaiting_signoff"
    assert held["decision"]["payout"] == 1150.0


def test_rate_limited_calls_are_retried_for_about_a_minute(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    llm = harness.model()
    assert llm.max_retries == harness.MAX_RETRIES
    assert llm.root_client.max_retries == harness.MAX_RETRIES
