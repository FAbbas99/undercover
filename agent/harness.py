"""The agent's harness: how one claim is worked, and how a run is worked.

Two agents are built here, both LangChain's `create_agent`. The worker decides
one claim. The queue runner hands each claim of a run to a fresh worker, so its
own context holds a line per claim rather than a claim's worth of reading.
"""

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import suppress
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agent import api
from agent.tools import CLAIM_TOOLS, QUEUE_TOOLS, ClaimContext, RunContext

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
# OpenRouter limits requests per minute. The client backs off up to 8 seconds per
# retry, so 12 retries wait out about a minute instead of failing the claim.
MAX_RETRIES = 12
# A worker gets this long on a claim before its run is ended for it.
CLAIM_TIMEOUT_SECONDS = float(os.getenv("CLAIM_TIMEOUT_SECONDS") or 120)
# A run of 25 claims takes about seven steps per claim.
QUEUE_STEPS = 300


class TimedOut(Exception):
    """The agent took too long over a claim."""


def model() -> ChatOpenAI:
    """Return the model named in MODEL_NAME, or DeepSeek V4.1 Flash."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
        max_retries=MAX_RETRIES,
    )


def within(seconds: float, action: Callable[[], Any]) -> Any:
    """Run something, giving up after a while.

    The work carries on in the background when the time is up, but the claim is
    no longer in progress by then, so the backend refuses anything it tries.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(action).result(timeout=seconds)
    except FutureTimeout:
        raise TimedOut(f"Timed out after {seconds:g} seconds") from None
    finally:
        pool.shutdown(wait=False)


def run_claim(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Decide one claim, and end its run however it goes."""
    try:
        agent = create_agent(
            llm or model(),
            tools=CLAIM_TOOLS,
            system_prompt=api.instructions("claim"),
            context_schema=ClaimContext,
        )
        result = within(
            CLAIM_TIMEOUT_SECONDS,
            lambda: agent.invoke(
                {
                    "messages": [
                        {"role": "user", "content": f"Decide claim {claim_id}."}
                    ]
                },
                config={"configurable": {"thread_id": thread_id}},
                context=ClaimContext(claim_id=claim_id),
            ),
        )
        note = result["messages"][-1].text or "Finished"
    except TimedOut as timed_out:
        note = str(timed_out)
    except Exception as error:
        note = f"Error: {error}"
    end_claim(claim_id, note)
    return note


def end_claim(claim_id: str, note: str) -> None:
    """End a claim's run, unless something has ended it already."""
    with suppress(api.Refused):
        api.finish_claim(claim_id, note)


def run_queue(run_id: str, llm: BaseChatModel | None = None) -> str:
    """Work a run's to-do list, and finish the run however it goes."""
    agent = create_agent(
        llm or model(),
        tools=QUEUE_TOOLS,
        system_prompt=api.instructions("queue"),
        context_schema=RunContext,
    )
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": f"Work run {run_id}."}]},
            config={
                "configurable": {"thread_id": run_id},
                "recursion_limit": QUEUE_STEPS,
            },
            context=RunContext(run_id=run_id),
        )
        note = result["messages"][-1].text or "Finished"
    except Exception as error:
        return abandon(run_id, f"The run stopped: {error}")
    if api.get_run(run_id)["finished_at"] is None:
        return abandon(run_id, note)
    return note


def abandon(run_id: str, note: str) -> str:
    """Leave a run's remaining claims for a handler, and finish the run."""
    for item in api.get_run(run_id)["items"]:
        if item["state"] in ("to_do", "in_progress"):
            api.set_run_item(run_id, item["claim_id"], "left_for_handler", note)
    with suppress(api.Refused):
        api.finish_run(run_id, note)
    return note
