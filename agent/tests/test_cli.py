"""The command line: a run over the queue, and one claim."""

import pytest
from fastapi.testclient import TestClient

import agent.__main__ as cli
from agent import api
from agent.harness import run_claim, run_queue
from agent.tests.e2e_server import QueueModel, ScriptedModel
from backend.main import agent_runner, app
from backend.runs import queue_runner

client = TestClient(app)


def use_models(worker=None, queue=None):
    app.dependency_overrides[agent_runner] = lambda: (
        lambda claim_id, thread_id: run_claim(
            claim_id, thread_id, worker or ScriptedModel(step_seconds=0)
        )
    )
    app.dependency_overrides[queue_runner] = lambda: (
        lambda run_id: run_queue(run_id, queue or QueueModel())
    )


def run_cli(*args):
    cli.main(list(args))


def test_decides_and_reports(capsys):
    use_models()
    run_cli("CLM-1001")
    out = capsys.readouterr().out
    assert "started" in out
    assert "record_decision" in out
    assert "Approve: $420.00" in out
    assert "Status: decided" in out
    assert "Paid: $420.00" in out


def test_over_the_limit_is_not_paid(capsys):
    use_models()
    run_cli("CLM-1002")
    out = capsys.readouterr().out
    assert "Approve: $1,150.00" in out
    assert "Status: awaiting_signoff" in out
    assert "Paid" not in out


def test_reports_a_run_with_no_decision(capsys):
    use_models(worker=ScriptedModel(step_seconds=0, fail=True))
    run_cli("CLM-1003")
    assert "No decision. Error: scripted failure" in capsys.readouterr().out


def test_waits_while_the_run_is_in_progress(monkeypatch, capsys):
    monkeypatch.setattr(cli, "POLL_SECONDS", 0)
    use_models()
    real_get_claim = api.get_claim
    polls = []

    def get_claim(claim_id):
        claim = real_get_claim(claim_id)
        if len(polls) == 1:
            claim["status"] = "in_progress"
        polls.append(claim_id)
        return claim

    monkeypatch.setattr(cli.api, "get_claim", get_claim)
    claim = cli.decide("CLM-1004")
    assert claim is not None
    assert claim["status"] == "decided"
    assert len(polls) == 3
    lines = capsys.readouterr().out.splitlines()
    assert [line for line in lines if "  started  " in line] == [lines[0]]


def test_refuses_a_claim_that_is_not_waiting(capsys):
    use_models()
    with pytest.raises(SystemExit) as exit_info:
        run_cli("CLM-9999")
    assert exit_info.value.code == 1
    assert "Refused: No claim CLM-9999" in capsys.readouterr().out


def test_usage(capsys):
    with pytest.raises(SystemExit, match="Usage"):
        run_cli("CLM-1001", "CLM-1002")


def test_starts_a_run_over_the_queue(capsys):
    use_models()
    run_cli()
    out = capsys.readouterr().out
    assert out.startswith("Run started over 25 claims.")
    assert "CLM-1001  done" in out
    assert "Worked 25 claims." in out
    assert not [c for c in api.claims() if c["status"] == "waiting"]


def test_starts_a_run_capped_for_a_trial(capsys):
    use_models()
    run_cli("--cap", "5")
    out = capsys.readouterr().out
    assert out.startswith("Run started over 5 claims.")
    assert "Worked 5 claims." in out
    assert len([c for c in api.claims() if c["status"] == "waiting"]) == 20


def test_follows_the_to_do_list(monkeypatch, capsys):
    """Every change in the to-do list is printed once, then the summary."""
    monkeypatch.setattr(cli, "POLL_SECONDS", 0)
    states = [
        {
            "items": [{"claim_id": "CLM-1001", "state": "to_do", "note": ""}],
            "finished_at": None,
        },
        {
            "items": [
                {"claim_id": "CLM-1001", "state": "in_progress", "note": "working"}
            ],
            "finished_at": None,
        },
        {
            "items": [
                {"claim_id": "CLM-1001", "state": "done", "note": "approve $420.00"}
            ],
            "finished_at": "2026-06-24T10:00:00Z",
            "summary": "One claim approved.",
        },
    ]
    monkeypatch.setattr(cli.api, "get_run", lambda run_id: states.pop(0))
    finished = cli.follow("R1")
    out = capsys.readouterr().out
    assert finished["summary"] == "One claim approved."
    assert [line.split() for line in out.splitlines()] == [
        ["CLM-1001", "to_do"],
        ["CLM-1001", "in_progress", "working"],
        ["CLM-1001", "done", "approve", "$420.00"],
    ]


def test_a_run_with_nothing_waiting(capsys):
    use_models()
    run_cli("--cap", "25")
    capsys.readouterr()
    run_cli("--cap", "5")
    assert "Refused: No claims are waiting" in capsys.readouterr().out
