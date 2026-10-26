"""The UnderCover backend."""

import json
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel, model_validator

from agent.main import run
from backend import documents
from backend.db import connect, record, records

HERE = Path(__file__).parent
CUSTOMER_FIELDS = ("customer_id", "name", "customer_since", "previous_claims")

app = FastAPI(title="UnderCover")

Runner = Callable[[str, str], object]


class Decision(BaseModel):
    outcome: Literal["approve", "decline", "refer"]
    payout: float
    reason: str
    policy_section: str

    @model_validator(mode="after")
    def payout_matches_outcome(self) -> Self:
        if self.outcome == "approve" and self.payout <= 0:
            raise ValueError("An approval needs a payout above 0")
        if self.outcome != "approve" and self.payout != 0:
            raise ValueError("A decline or a referral has a payout of 0")
        return self


class Payment(BaseModel):
    amount: float


class SignOff(BaseModel):
    handler_id: str


class Step(BaseModel):
    name: str
    detail: str


class Finish(BaseModel):
    note: str


def database() -> Iterator[sqlite3.Connection]:
    """Open a database connection for one request."""
    with closing(connect()) as conn:
        yield conn


Db = Annotated[sqlite3.Connection, Depends(database)]


def split(conn: sqlite3.Connection, setting: str) -> documents.Document:
    """Return one of the documents the seed loaded, split into sections."""
    return documents.read_document(record(conn, "setting", setting))


def wording(conn: sqlite3.Connection) -> documents.Document:
    """Return the policy wording, split into sections."""
    return split(conn, "policy_wording")


def manual(conn: sqlite3.Connection) -> documents.Document:
    """Return the claims manual, split into sections."""
    return split(conn, "claims_manual")


def section_or_404(document: documents.Document, number: str) -> documents.Section:
    """Return one section of a document, or raise 404."""
    try:
        return documents.find(document, number)
    except KeyError:
        raise HTTPException(404, f"No section {number}") from None


def instructions(name: str) -> dict[str, str]:
    """Get one of the UnderCover Agent's instruction documents."""
    return {"text": (HERE / f"instructions_{name}.md").read_text(encoding="utf-8")}


def approval_limit(conn: sqlite3.Connection) -> float:
    """Return the payout above which a handler must sign off."""
    return record(conn, "setting", "payout_approval_limit")


def status(conn: sqlite3.Connection, row: sqlite3.Row) -> str:
    """Work out where a claim stands from its record."""
    if row["in_progress"]:
        return "in_progress"
    if row["outcome"] is None:
        return "waiting"
    over_limit = row["outcome"] == "approve" and row["payout"] > approval_limit(conn)
    if over_limit and row["signed_off_by"] is None:
        return "awaiting_signoff"
    return "decided"


def claim_row(conn: sqlite3.Connection, claim_id: str) -> sqlite3.Row:
    """Return a claim's row, or raise 404."""
    row = conn.execute(
        "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"No claim {claim_id}")
    return row


def claim_view(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    """Return a claim in full, with its policy, plan, customer, decision and steps."""
    claim = json.loads(row["data"])
    del claim["status"]
    policy = record(conn, "policy", claim["policy_id"])
    customer = record(conn, "customer", claim["customer_id"])
    plan = record(conn, "plan", policy["plan"])
    plan["deductible_applies_to"] = record(conn, "setting", "deductible_applies_to")
    steps = conn.execute(
        "SELECT at, name, detail FROM steps WHERE claim_id = ? ORDER BY step_id",
        (row["claim_id"],),
    ).fetchall()
    decision = None
    if row["outcome"] is not None:
        decision = {
            key: row[key] for key in ("outcome", "payout", "reason", "policy_section")
        }
    payment = None
    if row["paid_amount"] is not None:
        payment = {"amount": row["paid_amount"], "signed_off_by": row["signed_off_by"]}
    return {
        **claim,
        "status": status(conn, row),
        "policy": policy,
        "plan": plan,
        "add_ons": [record(conn, "add_on", a) for a in policy["add_ons"]],
        "customer": {key: customer[key] for key in CUSTOMER_FIELDS},
        "decision": decision,
        "payment": payment,
        "steps": [dict(step) for step in steps],
    }


@app.get("/api/health", operation_id="health")
def health() -> dict[str, str]:
    """Check that the backend is running."""
    return {"status": "ok"}


@app.get("/api/claims", operation_id="list_claims")
def list_claims(conn: Db) -> list[dict[str, Any]]:
    """List every claim in the queue with where it stands and its decision."""
    rows = conn.execute("SELECT * FROM claims ORDER BY claim_id").fetchall()
    claims = []
    for row in rows:
        claim = json.loads(row["data"])
        customer = record(conn, "customer", claim["customer_id"])
        claims.append(
            {
                "claim_id": claim["claim_id"],
                "status": status(conn, row),
                "customer_name": customer["name"],
                "claim_type": claim["claim_type"],
                "summary": claim["summary"],
                "amount_claimed": claim["amount_claimed"],
                "submitted_on": claim["submitted_on"],
                "outcome": row["outcome"],
                "payout": row["payout"],
            }
        )
    return claims


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, conn: Db) -> dict[str, Any]:
    """Get a claim in full, with its policy, plan, customer, decision and steps."""
    return claim_view(conn, claim_row(conn, claim_id))


@app.get("/api/policy-wording/sections", operation_id="list_wording_sections")
def list_wording_sections(conn: Db) -> list[documents.Section]:
    """List the numbered sections of the policy wording."""
    return documents.outline(wording(conn))


@app.get("/api/policy-wording/{section}", operation_id="get_wording_section")
def get_wording_section(section: str, conn: Db) -> documents.Section:
    """Get one numbered section of the policy wording."""
    return section_or_404(wording(conn), section)


@app.get("/api/manual/sections", operation_id="list_manual_sections")
def list_manual_sections(conn: Db) -> list[documents.Section]:
    """List the numbered sections of the claims manual."""
    return documents.outline(manual(conn))


@app.get("/api/manual/{section}", operation_id="get_manual_section")
def get_manual_section(section: str, conn: Db) -> documents.Section:
    """Get one numbered section of the claims manual."""
    return section_or_404(manual(conn), section)


@app.get("/api/instructions/queue", operation_id="get_queue_instructions")
def get_queue_instructions() -> dict[str, str]:
    """Get the agent's instructions for running the queue."""
    return instructions("queue")


@app.get("/api/instructions/claim", operation_id="get_claim_instructions")
def get_claim_instructions() -> dict[str, str]:
    """Get the agent's instructions for working one claim."""
    return instructions("claim")


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers(conn: Db) -> list[dict[str, Any]]:
    """List the claims handlers."""
    return records(conn, "handler")


@app.get("/api/settings", operation_id="get_settings")
def get_settings(conn: Db) -> dict[str, float]:
    """Get the payout approval limit."""
    return {"payout_approval_limit": approval_limit(conn)}


def agent_runner() -> Runner:
    """Return the function that runs the agent on a claim."""
    return run


def require(condition: bool, message: str) -> None:
    """Refuse the request with 409 unless the condition holds."""
    if not condition:
        raise HTTPException(409, message)


def add_step_row(
    conn: sqlite3.Connection, claim_id: str, name: str, detail: str
) -> None:
    """Record one step of a run."""
    conn.execute(
        "INSERT INTO steps (claim_id, name, detail) VALUES (?, ?, ?)",
        (claim_id, name, detail),
    )


@app.post("/api/claims/{claim_id}/run", operation_id="run_agent", status_code=202)
def run_agent(
    claim_id: str,
    conn: Db,
    tasks: BackgroundTasks,
    runner: Annotated[Runner, Depends(agent_runner)],
) -> dict[str, Any]:
    """Start the UnderCover Agent on a waiting claim."""
    row = claim_row(conn, claim_id)
    require(status(conn, row) == "waiting", f"{claim_id} is not waiting")
    conn.execute("UPDATE claims SET in_progress = 1 WHERE claim_id = ?", (claim_id,))
    add_step_row(conn, claim_id, "started", "The agent started work on the claim")
    conn.commit()
    tasks.add_task(runner, claim_id, str(uuid.uuid4()))
    return claim_view(conn, claim_row(conn, claim_id))


@app.post("/api/claims/{claim_id}/steps", operation_id="add_step")
def add_step(claim_id: str, step: Step, conn: Db) -> dict[str, str]:
    """Record a step the agent took on a claim in progress."""
    row = claim_row(conn, claim_id)
    require(row["in_progress"], f"{claim_id} is not in progress")
    add_step_row(conn, claim_id, step.name, step.detail)
    conn.commit()
    return {"status": "recorded"}


@app.post("/api/claims/{claim_id}/finish", operation_id="finish_run")
def finish_run(claim_id: str, finish: Finish, conn: Db) -> dict[str, Any]:
    """End the agent's run on a claim, with a closing note."""
    row = claim_row(conn, claim_id)
    require(row["in_progress"], f"{claim_id} is not in progress")
    add_step_row(conn, claim_id, "finished", finish.note)
    conn.execute("UPDATE claims SET in_progress = 0 WHERE claim_id = ?", (claim_id,))
    conn.commit()
    return claim_view(conn, claim_row(conn, claim_id))


@app.post("/api/claims/{claim_id}/decision", operation_id="record_decision")
def record_decision(claim_id: str, decision: Decision, conn: Db) -> dict[str, Any]:
    """Record the agent's decision on a claim: approve, decline or refer."""
    row = claim_row(conn, claim_id)
    require(row["in_progress"], f"{claim_id} is not in progress")
    require(row["outcome"] is None, f"{claim_id} already has a decision")
    conn.execute(
        "UPDATE claims SET outcome = ?, payout = ?, reason = ?, policy_section = ?"
        " WHERE claim_id = ?",
        (
            decision.outcome,
            round(decision.payout, 2),
            decision.reason,
            decision.policy_section,
            claim_id,
        ),
    )
    conn.commit()
    return claim_view(conn, claim_row(conn, claim_id))


@app.post("/api/claims/{claim_id}/payment", operation_id="pay_claim")
def pay_claim(claim_id: str, payment: Payment, conn: Db) -> dict[str, Any]:
    """Pay an approved claim its payout; over the limit it needs a sign-off first."""
    row = claim_row(conn, claim_id)
    require(row["outcome"] == "approve", f"{claim_id} is not approved")
    require(row["paid_amount"] is None, f"{claim_id} is already paid")
    require(
        round(payment.amount, 2) == row["payout"],
        f"The amount must be the approved payout, {row['payout']:.2f}",
    )
    require(
        row["payout"] <= approval_limit(conn),
        f"A payout over {approval_limit(conn):,.2f} waits for a handler's sign-off",
    )
    conn.execute(
        "UPDATE claims SET paid_amount = payout WHERE claim_id = ?", (claim_id,)
    )
    conn.commit()
    return claim_view(conn, claim_row(conn, claim_id))


@app.post("/api/claims/{claim_id}/sign-off", operation_id="sign_off")
def sign_off(claim_id: str, sign: SignOff, conn: Db) -> dict[str, Any]:
    """Sign off an approval over the limit as a handler, which pays the claim."""
    row = claim_row(conn, claim_id)
    handler = record(conn, "handler", sign.handler_id)
    if handler is None:
        raise HTTPException(404, f"No handler {sign.handler_id}")
    if not handler["can_approve_over_limit"]:
        raise HTTPException(403, f"{handler['name']} cannot approve over the limit")
    require(
        status(conn, row) == "awaiting_signoff", f"{claim_id} is not awaiting sign-off"
    )
    conn.execute(
        "UPDATE claims SET signed_off_by = ?, paid_amount = payout WHERE claim_id = ?",
        (sign.handler_id, claim_id),
    )
    conn.commit()
    return claim_view(conn, claim_row(conn, claim_id))
