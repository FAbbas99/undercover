"""A run: the agent works a list of claims in one go."""

import sqlite3
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from agent.main import run_queue
from backend.db import record_step
from backend.deps import Db, require

router = APIRouter()

# A claim is left for a handler after this many failed attempts.
FAILURE_LIMIT = 2

# The runs being worked in this process. A run left unfinished by a restart is
# not in here, so the next run knows it was interrupted.
LIVE: set[str] = set()

Runner = Callable[[str], object]


class Start(BaseModel):
    cap: Annotated[int, Field(gt=0)]


class Item(BaseModel):
    state: Literal["to_do", "in_progress", "done", "left_for_handler"]
    note: str


class Summary(BaseModel):
    summary: str


def queue_runner() -> Runner:
    """Return the function that runs the queue."""
    return run_queue


def run_row(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    """Return a run's row, or raise 404."""
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"No run {run_id}")
    return row


def run_view(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    """Return a run with its to-do list."""
    items = conn.execute(
        "SELECT claim_id, state, note FROM run_items WHERE run_id = ?"
        " ORDER BY claim_id",
        (row["run_id"],),
    ).fetchall()
    return {
        "run_id": row["run_id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "cap": row["cap"],
        "summary": row["summary"],
        "items": [dict(item) for item in items],
    }


def waiting_claims(conn: sqlite3.Connection, cap: int) -> list[str]:
    """Return the claims a run should take, in the order it takes them."""
    rows = conn.execute(
        "SELECT claim_id FROM claims"
        " WHERE in_progress = 0 AND outcome IS NULL AND failures < ?"
        " ORDER BY claim_id LIMIT ?",
        (FAILURE_LIMIT, cap),
    ).fetchall()
    return [row["claim_id"] for row in rows]


def unfinished(conn: sqlite3.Connection, run_id: str) -> list[str]:
    """Return the claims a run has not finished with."""
    rows = conn.execute(
        "SELECT i.claim_id FROM run_items i JOIN claims c ON c.claim_id = i.claim_id"
        " WHERE i.run_id = ?"
        " AND (i.state IN ('to_do', 'in_progress')"
        "      OR (i.state = 'done' AND c.outcome IS NULL))"
        " ORDER BY i.claim_id",
        (run_id,),
    ).fetchall()
    return [row["claim_id"] for row in rows]


def recover(conn: sqlite3.Connection) -> None:
    """Close any run left unfinished, and put its claims back in the queue."""
    for row in conn.execute(
        "SELECT run_id FROM runs WHERE finished_at IS NULL"
    ).fetchall():
        conn.execute(
            "UPDATE runs SET finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),"
            " summary = ? WHERE run_id = ?",
            ("The run was interrupted", row["run_id"]),
        )
    for row in conn.execute(
        "SELECT claim_id FROM claims WHERE in_progress = 1"
    ).fetchall():
        record_step(conn, row["claim_id"], "finished", "The run was interrupted")
        conn.execute(
            "UPDATE claims SET in_progress = 0 WHERE claim_id = ?", (row["claim_id"],)
        )
    conn.commit()


def tracked(runner: Runner, run_id: str) -> None:
    """Work a run, remembering that it is live while it does."""
    LIVE.add(run_id)
    try:
        runner(run_id)
    finally:
        LIVE.discard(run_id)


@router.post("/api/runs", operation_id="start_run", status_code=202)
def start_run(
    start: Start,
    conn: Db,
    tasks: BackgroundTasks,
    runner: Annotated[Runner, Depends(queue_runner)],
) -> dict[str, Any]:
    """Start a run over the waiting claims, up to the cap."""
    require(not LIVE, "A run is already in progress")
    recover(conn)
    claim_ids = waiting_claims(conn, start.cap)
    require(bool(claim_ids), "No claims are waiting")
    run_id = str(uuid.uuid4())
    conn.execute("INSERT INTO runs (run_id, cap) VALUES (?, ?)", (run_id, start.cap))
    conn.executemany(
        "INSERT INTO run_items (run_id, claim_id, state) VALUES (?, ?, 'to_do')",
        [(run_id, claim_id) for claim_id in claim_ids],
    )
    conn.commit()
    tasks.add_task(tracked, runner, run_id)
    return run_view(conn, run_row(conn, run_id))


@router.get("/api/runs/current", operation_id="get_current_run")
def get_current_run(conn: Db) -> dict[str, Any] | None:
    """Get the most recent run and its to-do list, or nothing before the first."""
    row = conn.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return run_view(conn, row) if row else None


@router.get("/api/runs/{run_id}", operation_id="get_run")
def get_run(run_id: str, conn: Db) -> dict[str, Any]:
    """Get one run and its to-do list."""
    return run_view(conn, run_row(conn, run_id))


@router.post("/api/runs/{run_id}/items/{claim_id}", operation_id="set_run_item")
def set_run_item(run_id: str, claim_id: str, item: Item, conn: Db) -> dict[str, Any]:
    """Set where a claim has got to in a run's to-do list."""
    run_row(conn, run_id)
    updated = conn.execute(
        "UPDATE run_items SET state = ?, note = ? WHERE run_id = ? AND claim_id = ?",
        (item.state, item.note, run_id, claim_id),
    )
    if updated.rowcount == 0:
        raise HTTPException(404, f"{claim_id} is not in run {run_id}")
    conn.commit()
    return run_view(conn, run_row(conn, run_id))


@router.post("/api/runs/{run_id}/finish", operation_id="finish_queue_run")
def finish_queue_run(run_id: str, finish: Summary, conn: Db) -> dict[str, Any]:
    """Finish a run with a summary, once every claim in it is decided or left."""
    row = run_row(conn, run_id)
    require(row["finished_at"] is None, f"Run {run_id} has already finished")
    left = unfinished(conn, run_id)
    require(not left, f"Still to work: {', '.join(left)}")
    conn.execute(
        "UPDATE runs SET finished_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),"
        " summary = ? WHERE run_id = ?",
        (finish.summary, run_id),
    )
    conn.commit()
    return run_view(conn, run_row(conn, run_id))
