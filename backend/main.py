"""The UnderCover backend."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException

from backend.db import connect, record, records

INSTRUCTIONS = Path(__file__).parent / "instructions.md"
CUSTOMER_FIELDS = ("customer_id", "name", "customer_since", "previous_claims")

app = FastAPI(title="UnderCover")


def database() -> Iterator[sqlite3.Connection]:
    """Open a database connection for one request."""
    with closing(connect()) as conn:
        yield conn


Db = Annotated[sqlite3.Connection, Depends(database)]


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
    """List every claim in the queue with where it stands."""
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
            }
        )
    return claims


@app.get("/api/claims/{claim_id}", operation_id="get_claim")
def get_claim(claim_id: str, conn: Db) -> dict[str, Any]:
    """Get a claim in full, with its policy, plan, customer, decision and steps."""
    return claim_view(conn, claim_row(conn, claim_id))


@app.get("/api/policy-wording", operation_id="get_policy_wording")
def get_policy_wording(conn: Db) -> dict[str, str]:
    """Get the policy wording, the contract that decisions follow."""
    return {"text": record(conn, "setting", "policy_wording")}


@app.get("/api/instructions", operation_id="get_instructions")
def get_instructions() -> dict[str, str]:
    """Get the UnderCover Agent's instructions."""
    return {"text": INSTRUCTIONS.read_text(encoding="utf-8")}


@app.get("/api/handlers", operation_id="list_handlers")
def list_handlers(conn: Db) -> list[dict[str, Any]]:
    """List the claims handlers."""
    return records(conn, "handler")


@app.get("/api/settings", operation_id="get_settings")
def get_settings(conn: Db) -> dict[str, float]:
    """Get the payout approval limit."""
    return {"payout_approval_limit": approval_limit(conn)}
