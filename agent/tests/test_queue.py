"""The queue runner: the to-do list, the retries and the failures."""

from fastapi.testclient import TestClient
from langchain_core.messages import ToolMessage
from pydantic import Field

from agent import api, harness
from agent.harness import run_claim, run_queue
from agent.tests.e2e_server import (
    QueueModel,
    ScriptedModel,
    reply,
    results_of,
    say,
)
from agent.tests.test_agent import decision, scripted
from backend.main import agent_runner, app
from backend.runs import queue_runner

client = TestClient(app)
prompts = []


class FailingWorker(ScriptedModel):
    """A worker that fails on the claims named, as a provider outage would."""

    failing: set[str] = Field(default_factory=set)

    def _generate(self, messages, *args, **kwargs):
        claim_id = str(messages[1].content).split()[-1].rstrip(".")
        if claim_id in self.failing:
            raise RuntimeError("scripted failure")
        return super()._generate(messages, *args, **kwargs)


class Watched(QueueModel):
    """The queue model, recording the system prompt it was given."""

    def _generate(self, messages, *args, **kwargs):
        prompts.append(str(messages[0].content))
        return super()._generate(messages, *args, **kwargs)


def work_the_queue(cap, worker=None, queue=None):
    app.dependency_overrides[agent_runner] = lambda: (
        lambda claim_id, thread_id: run_claim(
            claim_id, thread_id, worker or ScriptedModel(step_seconds=0)
        )
    )
    app.dependency_overrides[queue_runner] = lambda: (
        lambda run_id: run_queue(run_id, queue or QueueModel())
    )
    started = api.start_run(cap)
    return api.get_run(started["run_id"])


def items(run):
    return [(item["claim_id"], item["state"]) for item in run["items"]]


def test_a_run_works_every_claim_in_it():
    run = work_the_queue(3)
    assert items(run) == [
        ("CLM-1001", "done"),
        ("CLM-1002", "done"),
        ("CLM-1003", "done"),
    ]
    assert run["finished_at"] is not None
    assert run["summary"] == "Worked 3 claims."
    claims = {c["claim_id"]: c for c in api.claims()}
    assert claims["CLM-1001"]["status"] == "decided"
    assert claims["CLM-1002"]["status"] == "awaiting_signoff"
    assert claims["CLM-1003"]["status"] == "awaiting_signoff"
    assert claims["CLM-1004"]["status"] == "waiting"


def test_each_claim_keeps_its_own_steps():
    work_the_queue(2)
    assert names_of("CLM-1001") == [
        "started",
        "get_claim",
        "record_decision",
        "pay_claim",
        "finished",
    ]
    assert names_of("CLM-1002") == [
        "started",
        "get_claim",
        "record_decision",
        "finished",
    ]


def names_of(claim_id):
    return [step["name"] for step in api.get_claim(claim_id)["steps"]]


def test_the_runner_uses_the_served_instructions():
    prompts.clear()
    work_the_queue(1, queue=Watched())
    assert prompts[0] == client.get("/api/instructions/queue").json()["text"]


def test_a_failed_claim_is_tried_again():
    run = work_the_queue(1, worker=ScriptedModel(step_seconds=0, fail=True))
    assert run["finished_at"] is not None
    assert run["summary"] == "Worked 1 claims."
    assert api.get_claim("CLM-1001")["failures"] == 2


def test_a_claim_that_fails_twice_is_left_for_a_handler():
    run = work_the_queue(1, worker=ScriptedModel(step_seconds=0, fail=True))
    assert items(run) == [("CLM-1001", "left_for_handler")]
    assert "failed" in run["items"][0]["note"]
    assert api.get_claim("CLM-1001")["status"] == "waiting"
    assert api.start_run(1)["items"][0]["claim_id"] == "CLM-1002"


def test_one_bad_claim_does_not_stop_the_run():
    run = work_the_queue(3, worker=FailingWorker(step_seconds=0, failing={"CLM-1002"}))
    assert run["finished_at"] is not None
    assert items(run) == [
        ("CLM-1001", "done"),
        ("CLM-1002", "left_for_handler"),
        ("CLM-1003", "done"),
    ]
    claims = {c["claim_id"]: c for c in api.claims()}
    assert claims["CLM-1001"]["status"] == "decided"
    assert claims["CLM-1003"]["status"] == "awaiting_signoff"


def test_a_claim_that_fails_once_is_worked_on_the_second_try():
    class Flaky(FailingWorker):
        """Fails the first time a claim is worked, and answers the second."""

        seen: dict[str, int] = Field(default_factory=dict)

        def _generate(self, messages, *args, **kwargs):
            claim_id = str(messages[1].content).split()[-1].rstrip(".")
            self.seen[claim_id] = self.seen.get(claim_id, 0) + 1
            self.failing = {claim_id} if self.seen[claim_id] == 1 else set()
            return super()._generate(messages, *args, **kwargs)

    run = work_the_queue(1, worker=Flaky(step_seconds=0))
    assert items(run) == [("CLM-1001", "done")]
    assert api.get_claim("CLM-1001")["failures"] == 1
    assert api.get_claim("CLM-1001")["status"] == "decided"


def test_the_run_cannot_be_finished_with_a_claim_to_do():
    class TooSoon(QueueModel):
        """Tries to finish the run before working any claim."""

        def _generate(self, messages, *args, **kwargs):
            if not results_of(messages):
                return reply("finish_queue_run", {"summary": "Done already."})
            return say(f"Tried to finish: {results_of(messages)[-1]}")

    run = work_the_queue(2, queue=TooSoon())
    assert run["summary"] == (
        "Tried to finish: Refused: Still to work: CLM-1001, CLM-1002"
    )
    assert items(run) == [
        ("CLM-1001", "left_for_handler"),
        ("CLM-1002", "left_for_handler"),
    ]


def test_a_run_that_stops_leaves_its_claims_for_a_handler():
    class Broken(QueueModel):
        """A runner whose model fails part way through."""

        def _generate(self, messages, *args, **kwargs):
            if not [m for m in messages if isinstance(m, ToolMessage)]:
                return super()._generate(messages, *args, **kwargs)
            raise RuntimeError("provider down")

    run = work_the_queue(2, queue=Broken())
    assert run["finished_at"] is not None
    assert items(run) == [
        ("CLM-1001", "left_for_handler"),
        ("CLM-1002", "left_for_handler"),
    ]
    assert run["summary"].startswith("The run stopped: ")


def test_a_second_decision_does_not_stop_the_run():
    run = work_the_queue(
        1,
        worker=scripted(
            ("get_claim", {}),
            decision("approve", 420.0),
            decision("approve", 420.0),
            ("pay_claim", {"amount": 420.0}),
            final="Decided once.",
        ),
    )
    assert items(run) == [("CLM-1001", "done")]
    assert api.get_claim("CLM-1001")["decision"]["payout"] == 420.0
    assert api.get_claim("CLM-1001")["payment"] == {
        "amount": 420.0,
        "signed_off_by": None,
    }


def test_the_queue_runner_is_the_harness():
    assert queue_runner() is harness.run_queue
