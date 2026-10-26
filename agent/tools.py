"""The agent's tools: the claim tools and the queue tools.

Each tool is a call to the backend, and each one records what it did on the
claim, so a handler can watch the work as it happens. A tool's claim or run
comes from its context, so the model never has to carry an id around.
"""

import json
import time
from dataclasses import dataclass
from typing import Literal

from langchain.tools import ToolRuntime, tool

from agent import api

POLL_SECONDS = 0.5
CLAIM_WAIT_SECONDS = 600


@dataclass
class ClaimContext:
    """The claim a worker is deciding."""

    claim_id: str


@dataclass
class RunContext:
    """The run a queue runner is working."""

    run_id: str


@tool
def get_claim(runtime: ToolRuntime[ClaimContext]) -> str:
    """Get the claim in full: the story, items, documents, policy and history."""
    claim_id = runtime.context.claim_id
    claim = api.get_claim(claim_id)
    api.add_step(claim_id, "get_claim", claim_id)
    return json.dumps(claim)


@tool
def list_wording_sections(runtime: ToolRuntime[ClaimContext]) -> str:
    """List the numbered sections of the policy wording."""
    return json.dumps(api.wording_sections())


@tool
def get_wording_section(runtime: ToolRuntime[ClaimContext], section: str) -> str:
    """Read one numbered section of the policy wording."""
    return read(runtime.context.claim_id, "read_wording", api.wording_section(section))


@tool
def list_manual_sections(runtime: ToolRuntime[ClaimContext]) -> str:
    """List the numbered sections of the claims manual."""
    return json.dumps(api.manual_sections())


@tool
def get_manual_section(runtime: ToolRuntime[ClaimContext], section: str) -> str:
    """Read one numbered section of the claims manual."""
    return read(runtime.context.claim_id, "read_manual", api.manual_section(section))


def read(claim_id: str, name: str, section: dict[str, str]) -> str:
    """Record the section that was read, then give it to the model."""
    api.add_step(claim_id, name, f"{section['section']}. {section['title']}")
    return section["text"]


@tool
def record_decision(
    runtime: ToolRuntime[ClaimContext],
    outcome: Literal["approve", "decline", "refer"],
    payout: float,
    reason: str,
    policy_section: str,
) -> str:
    """Record the claim's decision, once: the payout is 0 unless approved."""
    claim_id = runtime.context.claim_id
    try:
        api.record_decision(claim_id, outcome, payout, reason, policy_section)
    except api.Refused as refused:
        return f"Refused: {refused}"
    api.add_step(claim_id, "record_decision", f"{outcome} ${payout:,.2f}")
    return f"{outcome} recorded"


@tool
def pay_claim(runtime: ToolRuntime[ClaimContext], amount: float) -> str:
    """Pay the claim its payout. Over $1,000 it waits for a sign-off."""
    claim_id = runtime.context.claim_id
    try:
        api.pay_claim(claim_id, amount)
    except api.Refused as refused:
        return f"Refused: {refused}"
    api.add_step(claim_id, "pay_claim", f"${amount:,.2f}")
    return "Paid"


@tool
def get_run(runtime: ToolRuntime[RunContext]) -> str:
    """Get the run's to-do list, with where each claim has got to."""
    return json.dumps(api.get_run(runtime.context.run_id))


@tool
def work_claim(runtime: ToolRuntime[RunContext], claim_id: str) -> str:
    """Hand one claim to a fresh worker, wait for it, and answer in a line."""
    try:
        api.start_claim(claim_id)
    except api.Refused as refused:
        return f"{claim_id} failed: {refused}"
    deadline = time.monotonic() + CLAIM_WAIT_SECONDS
    while time.monotonic() < deadline:
        claim = api.get_claim(claim_id)
        if claim["status"] != "in_progress":
            return report(claim)
        time.sleep(POLL_SECONDS)
    api.finish_claim(claim_id, "No answer from the worker")
    return f"{claim_id} failed: no answer from the worker"


def report(claim: dict) -> str:
    """Describe where a claim ended up, in one line."""
    decision = claim["decision"]
    if decision is None:
        steps = claim["steps"]
        detail = steps[-1]["detail"] if steps else "no steps"
        return f"{claim['claim_id']} failed: {detail}"
    return (
        f"{claim['claim_id']} {decision['outcome']} ${decision['payout']:,.2f},"
        f" status {claim['status']}"
    )


@tool
def set_run_item(
    runtime: ToolRuntime[RunContext],
    claim_id: str,
    state: Literal["to_do", "in_progress", "done", "left_for_handler"],
    note: str,
) -> str:
    """Set where a claim has got to in the run's to-do list."""
    api.set_run_item(runtime.context.run_id, claim_id, state, note)
    return f"{claim_id} is {state}"


@tool
def finish_queue_run(runtime: ToolRuntime[RunContext], summary: str) -> str:
    """Finish the run, with a short summary for the handlers."""
    try:
        api.finish_run(runtime.context.run_id, summary)
    except api.Refused as refused:
        return f"Refused: {refused}"
    return "The run is finished"


CLAIM_TOOLS = [
    get_claim,
    list_wording_sections,
    get_wording_section,
    list_manual_sections,
    get_manual_section,
    record_decision,
    pay_claim,
]

QUEUE_TOOLS = [get_run, work_claim, set_run_item, finish_queue_run]
