"""The backend for the end-to-end tests: a fresh database and a scripted model.

Run with `uv run -m agent.tests.e2e_server`. It never calls a real model.
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
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent import main as agent
from backend.main import agent_runner, app

PORT = 8001
STEP_SECONDS = 0.6


class ScriptedModel(BaseChatModel):
    """Reads the claim, approves the amount claimed, pays it, then says so."""

    step_seconds: float = STEP_SECONDS
    fail: bool = False

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        return self

    def _generate(
        self, messages: list[BaseMessage], *args: Any, **kwargs: Any
    ) -> ChatResult:
        time.sleep(self.step_seconds)
        if self.fail:
            raise RuntimeError("scripted failure")
        claim_id = str(messages[1].content).split()[-1].rstrip(".")
        results = [m for m in messages if isinstance(m, ToolMessage)]
        amount = (
            json.loads(str(results[0].content))["amount_claimed"] if results else 0.0
        )
        calls = [
            ("get_claim", {"claim_id": claim_id}),
            (
                "record_decision",
                {
                    "claim_id": claim_id,
                    "outcome": "approve",
                    "payout": amount,
                    "reason": "The scripted model approves the amount claimed.",
                    "policy_section": "10. How we work out your payment",
                },
            ),
            ("pay_claim", {"claim_id": claim_id, "amount": amount}),
        ]
        if len(results) < len(calls):
            name, args = calls[len(results)]
            reply = AIMessage(
                content="",
                tool_calls=[{"name": name, "args": args, "id": str(len(results))}],
            )
        else:
            reply = AIMessage(content=f"Approved {claim_id} for the amount claimed.")
        return ChatResult(generations=[ChatGeneration(message=reply)])


def serve() -> None:
    """Start the backend on a fresh database with the scripted model."""
    os.environ["UNDERCOVER_DB"] = str(Path(tempfile.mkdtemp()) / "e2e.db")
    url = f"http://127.0.0.1:{PORT}"
    agent.backend = lambda: httpx.Client(base_url=url, timeout=30)
    app.dependency_overrides[agent_runner] = lambda: (
        lambda claim_id, thread_id: agent.run(claim_id, thread_id, ScriptedModel())
    )
    uvicorn.run(app, host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    serve()
