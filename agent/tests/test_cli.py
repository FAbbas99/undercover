import json

import pytest
from fastapi.testclient import TestClient

import agent.__main__ as cli
from agent import main
from agent.tests.e2e_server import ScriptedModel
from backend.main import agent_runner, app


@pytest.fixture(autouse=True)
def in_process(monkeypatch):
    monkeypatch.setattr(main, "backend", lambda: TestClient(app))
    yield
    app.dependency_overrides.clear()


def use_model(llm):
    app.dependency_overrides[agent_runner] = lambda: lambda c, t: main.run(c, t, llm)


def run_cli(*args):
    cli.main(list(args))


def test_decides_and_reports(monkeypatch, capsys):
    use_model(ScriptedModel(step_seconds=0))
    run_cli("CLM-1001")
    out = capsys.readouterr().out
    assert "started" in out
    assert "record_decision" in out
    assert "Approve: $420.00" in out
    assert "Status: decided" in out
    assert "Paid: $420.00" in out


def test_over_the_limit_is_not_paid(monkeypatch, capsys):
    use_model(ScriptedModel(step_seconds=0))
    run_cli("CLM-1002")
    out = capsys.readouterr().out
    assert "Approve: $1,150.00" in out
    assert "Status: awaiting_signoff" in out
    assert "Paid" not in out


def test_reports_a_run_with_no_decision(monkeypatch, capsys):
    use_model(ScriptedModel(step_seconds=0, fail=True))
    run_cli("CLM-1003")
    assert "No decision. Error: scripted failure" in capsys.readouterr().out


def test_waits_while_the_run_is_in_progress(monkeypatch, capsys):
    monkeypatch.setattr(cli, "POLL_SECONDS", 0)
    use_model(ScriptedModel(step_seconds=0))
    gets = []
    real_call = cli.call

    def call(method, path, body=None):
        reply = real_call(method, path, body)
        if method == "GET" and not gets:
            gets.append(path)
            claim = json.loads(reply)
            claim["status"] = "in_progress"
            return json.dumps(claim)
        return reply

    monkeypatch.setattr(cli, "call", call)
    claim = cli.decide("CLM-1004")
    assert claim is not None
    assert claim["status"] == "decided"
    assert capsys.readouterr().out.count("started") == 1


def test_refuses_a_claim_that_is_not_waiting(capsys):
    with pytest.raises(SystemExit) as exit_info:
        run_cli("CLM-9999")
    assert exit_info.value.code == 1
    assert "Refused: No claim CLM-9999" in capsys.readouterr().out


def test_usage():
    with pytest.raises(SystemExit, match="Usage"):
        run_cli("CLM-1001", "CLM-1002")


def test_runs_every_waiting_claim(capsys):
    use_model(ScriptedModel(step_seconds=0))
    run_cli()
    out = capsys.readouterr().out
    assert out.startswith("25 claims are waiting.")
    assert "CLM-1001  approve" in out
    assert "Ran 25 claims: 10 awaiting_signoff, 15 decided" in out
    assert "Refused" not in out
    claims = TestClient(app).get("/api/claims").json()
    assert not [c for c in claims if c["status"] == "waiting"]


def test_skips_claims_that_are_not_waiting(capsys):
    use_model(ScriptedModel(step_seconds=0))
    run_cli("CLM-1001")
    capsys.readouterr()
    run_cli()
    out = capsys.readouterr().out
    assert out.startswith("24 claims are waiting.")
    assert "\nCLM-1001\n" not in out
    assert "Ran 24 claims" in out


def test_carries_on_when_a_run_is_refused(monkeypatch, capsys):
    use_model(ScriptedModel(step_seconds=0, fail=True))
    monkeypatch.setattr(cli, "waiting_claims", lambda: ["CLM-1001", "CLM-9999"])
    run_cli()
    out = capsys.readouterr().out
    assert "Refused: No claim CLM-9999" in out
    assert "CLM-1001  no decision" in out
    assert "Ran 1 claims: 1 waiting" in out
    assert "Refused to start: 1" in out


def test_nothing_waiting(monkeypatch, capsys):
    monkeypatch.setattr(cli, "waiting_claims", lambda: [])
    run_cli()
    assert capsys.readouterr().out == "No claims are waiting.\n"
