"""The backend for the end-to-end tests: a fresh database and scripted models.

Run with `uv run -m agent.tests.e2e_server`. No model is ever called.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agent import api, harness
from backend.main import agent_runner, app
from backend.runs import queue_runner

PORT = 8001
STEP_SECONDS = 0.6


def reply(name: str, args: dict[str, Any]) -> ChatResult:
    """Answer with one tool call."""
    message = AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": name}]
    )
    return ChatResult(generations=[ChatGeneration(message=message)])


def say(text: str) -> ChatResult:
    """Answer with a closing line."""
    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


def results_of(messages: list[Any]) -> list[str]:
    """The replies the tools have already given."""
    return [
        str(message.content) for message in messages if isinstance(message, ToolMessage)
    ]


class ScriptedModel(BaseChatModel):
    """Works one claim: reads it, approves the amount claimed, pays it, says so."""

    step_seconds: float = STEP_SECONDS
    fail: bool = False

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        return self

    def _generate(self, messages: list[Any], *args: Any, **kwargs: Any) -> ChatResult:
        time.sleep(self.step_seconds)
        if self.fail:
            raise RuntimeError("scripted failure")
        claim_id = str(messages[1].content).split()[-1].rstrip(".")
        results = results_of(messages)
        amount = json.loads(results[0])["amount_claimed"] if results else 0.0
        calls: list[tuple[str, dict[str, Any]]] = [
            ("get_claim", {}),
            ("get_wording_section", {"section": "3"}),
            (
                "record_decision",
                {
                    "outcome": "approve",
                    "payout": amount,
                    "reason": "The scripted model approves the amount claimed.",
                    "policy_section": "10. How we work out your payment",
                },
            ),
            ("pay_claim", {"amount": amount}),
        ]
        if len(results) < len(calls):
            name, tool_args = calls[len(results)]
            return reply(name, tool_args)
        return say(f"Approved {claim_id} for the amount claimed.")


class QueueModel(BaseChatModel):
    """Works a run: every claim through a fresh worker, retrying a failure once.

    It reads the to-do list again whenever it has changed something, so it
    always works from the list the backend holds.
    """

    step_seconds: float = 0.0
    attempts: dict[str, int] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "queue"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "QueueModel":
        return self

    def _generate(self, messages: list[Any], *args: Any, **kwargs: Any) -> ChatResult:
        time.sleep(self.step_seconds)
        results = results_of(messages)
        if not results:
            return reply("get_run", {})
        last = results[-1]
        run = as_run(last)
        if run is not None:
            return self.from_the_list(run)
        if " is " in last:
            return reply("get_run", {})
        return self.from_the_worker(last)

    def from_the_list(self, run: dict[str, Any]) -> ChatResult:
        """Work the first claim the to-do list still has to do."""
        pending = [
            item for item in run["items"] if item["state"] in ("to_do", "in_progress")
        ]
        if not pending:
            return reply(
                "finish_queue_run",
                {"summary": f"Worked {len(run['items'])} claims."},
            )
        item = pending[0]
        if item["state"] == "to_do":
            return reply(
                "set_run_item",
                {
                    "claim_id": item["claim_id"],
                    "state": "in_progress",
                    "note": "working",
                },
            )
        return reply("work_claim", {"claim_id": item["claim_id"]})

    def from_the_worker(self, report: str) -> ChatResult:
        """Mark a claim done, or retry it once and then leave it for a handler."""
        claim_id = report.split(maxsplit=1)[0]
        if " failed: " not in report:
            return reply(
                "set_run_item", {"claim_id": claim_id, "state": "done", "note": report}
            )
        self.attempts[claim_id] = self.attempts.get(claim_id, 0) + 1
        if self.attempts[claim_id] == 1:
            return reply("work_claim", {"claim_id": claim_id})
        return reply(
            "set_run_item",
            {"claim_id": claim_id, "state": "left_for_handler", "note": report},
        )


def as_run(text: str) -> dict[str, Any] | None:
    """The text as a run, if it is one."""
    try:
        run = json.loads(text)
    except json.JSONDecodeError:
        return None
    return run if isinstance(run, dict) and "items" in run else None


def serve() -> None:
    """Start the backend on a fresh database with the scripted models."""
    os.environ["UNDERCOVER_DB"] = str(Path(tempfile.mkdtemp()) / "e2e.db")
    api.client = lambda: httpx.Client(  # pyright: ignore[reportAttributeAccessIssue]
        base_url=f"http://127.0.0.1:{PORT}", timeout=30
    )
    app.dependency_overrides[agent_runner] = lambda: (
        lambda claim_id, thread_id: harness.run_claim(
            claim_id, thread_id, ScriptedModel()
        )
    )
    app.dependency_overrides[queue_runner] = lambda: (
        lambda run_id: harness.run_queue(run_id, QueueModel())
    )
    uvicorn.run(app, host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    serve()
