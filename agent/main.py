"""The UnderCover Agent."""

import json
import os
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

load_dotenv(override=True)

BACKEND_URL = "http://localhost:8000"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"
# OpenRouter limits requests per minute. The client backs off up to 8 seconds per
# retry, so 12 retries wait out about a minute instead of failing the claim.
MAX_RETRIES = 12


def backend() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def call(method: str, path: str, body: dict[str, Any] | None = None) -> str:
    """Call the backend and return its reply, or the reason it refused."""
    with backend() as client:
        response = client.request(method, path, json=body)
    if response.is_client_error:
        return f"Refused: {response.json()['detail']}"
    response.raise_for_status()
    return response.text


@tool
def get_claim(claim_id: str) -> str:
    """Get a claim in full: the story, items, documents, policy, plan and history."""
    return call("GET", f"/api/claims/{claim_id}")


@tool
def get_policy_wording() -> str:
    """Get the policy wording, the contract that decisions follow."""
    return json.loads(call("GET", "/api/policy-wording"))["text"]


@tool
def record_decision(
    claim_id: str,
    outcome: Literal["approve", "decline", "refer"],
    payout: float,
    reason: str,
    policy_section: str,
) -> str:
    """Record the decision on a claim, once: the payout is 0 unless approved."""
    return call(
        "POST",
        f"/api/claims/{claim_id}/decision",
        {
            "outcome": outcome,
            "payout": payout,
            "reason": reason,
            "policy_section": policy_section,
        },
    )


@tool
def pay_claim(claim_id: str, amount: float) -> str:
    """Pay an approved claim its payout. Over $1,000 it waits for a sign-off."""
    return call("POST", f"/api/claims/{claim_id}/payment", {"amount": amount})


TOOLS = [get_claim, get_policy_wording, record_decision, pay_claim]


class StepRecorder(BaseCallbackHandler):
    """Record each tool call as a step on the claim."""

    def __init__(self, claim_id: str) -> None:
        self.claim_id = claim_id

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        call(
            "POST",
            f"/api/claims/{self.claim_id}/steps",
            {"name": serialized["name"], "detail": input_str},
        )


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or GPT-6 Luna by default."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
        max_retries=MAX_RETRIES,
    )


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Run the agent on one claim, finish the run and return its final reply."""
    instructions = json.loads(call("GET", "/api/instructions"))["text"]
    try:
        agent = create_agent(llm or model(), tools=TOOLS, system_prompt=instructions)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": f"Decide claim {claim_id}."}]},
            config={
                "configurable": {"thread_id": thread_id},
                "callbacks": [StepRecorder(claim_id)],
            },
        )
        note = result["messages"][-1].text or "Finished"
    except Exception as error:
        note = f"Error: {error}"
    call("POST", f"/api/claims/{claim_id}/finish", {"note": note})
    return note
