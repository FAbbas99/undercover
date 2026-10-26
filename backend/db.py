"""The UnderCover database: SQLite, seeded from named files in data/."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
SEED_FILES = [
    "claims.json",
    "policies.json",
    "customers.json",
    "plans.json",
    "handlers.json",
    "company.json",
    "policy_wording.md",
    "claims_manual.md",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    in_progress INTEGER NOT NULL DEFAULT 0,
    outcome TEXT,
    payout REAL,
    reason TEXT,
    policy_section TEXT,
    paid_amount REAL,
    signed_off_by TEXT,
    failures INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS records (
    kind TEXT, record_id TEXT, data TEXT, PRIMARY KEY (kind, record_id)
);
CREATE TABLE IF NOT EXISTS steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    name TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at TEXT,
    cap INTEGER NOT NULL,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS run_items (
    run_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    state TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, claim_id)
);
"""


def db_path() -> Path:
    """Return the database path, from UNDERCOVER_DB or the repo root."""
    return Path(os.getenv("UNDERCOVER_DB", ROOT / "undercover.db"))


def read(name: str) -> str:
    """Read one of the seed files."""
    return (DATA / name).read_text(encoding="utf-8")


def seed(conn: sqlite3.Connection) -> None:
    """Create the tables and load the seed files."""
    conn.executescript(SCHEMA)
    files = {name: read(name) for name in SEED_FILES}
    claims = json.loads(files["claims.json"])
    conn.executemany(
        "INSERT INTO claims (claim_id, data) VALUES (?, ?)",
        [(c["claim_id"], json.dumps(c)) for c in claims],
    )
    plans = json.loads(files["plans.json"])
    company = json.loads(files["company.json"])
    records = [
        *[("policy", p["policy_id"], p) for p in json.loads(files["policies.json"])],
        *[
            ("customer", c["customer_id"], c)
            for c in json.loads(files["customers.json"])
        ],
        *[("handler", h["handler_id"], h) for h in json.loads(files["handlers.json"])],
        *[("plan", p["plan"], p) for p in plans["plans"]],
        *[("add_on", a["add_on"], a) for a in plans["add_ons"]],
        ("setting", "deductible_applies_to", plans["deductible_applies_to"]),
        ("setting", "payout_approval_limit", company["payout_approval_limit"]),
        ("setting", "policy_wording", files["policy_wording.md"]),
        ("setting", "claims_manual", files["claims_manual.md"]),
    ]
    conn.executemany(
        "INSERT INTO records VALUES (?, ?, ?)",
        [(kind, rid, json.dumps(data)) for kind, rid, data in records],
    )
    conn.commit()


def connect() -> sqlite3.Connection:
    """Open the database, creating, seeding and updating it as needed."""
    # FastAPI may open a request's connection and use it in different threads.
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'claims'").fetchone():
        seed(conn)
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Add the tables and columns a database from an earlier build is missing."""
    conn.executescript(SCHEMA)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(claims)")}
    if "failures" not in columns:
        conn.execute(
            "ALTER TABLE claims ADD COLUMN failures INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()


def record_step(
    conn: sqlite3.Connection, claim_id: str, name: str, detail: str
) -> None:
    """Record one step of a run."""
    conn.execute(
        "INSERT INTO steps (claim_id, name, detail) VALUES (?, ?, ?)",
        (claim_id, name, detail),
    )


def record(conn: sqlite3.Connection, kind: str, record_id: str) -> Any:
    """Return one record by kind and id, or None."""
    row = conn.execute(
        "SELECT data FROM records WHERE kind = ? AND record_id = ?", (kind, record_id)
    ).fetchone()
    return json.loads(row["data"]) if row else None


def records(conn: sqlite3.Connection, kind: str) -> list[Any]:
    """Return every record of a kind."""
    rows = conn.execute("SELECT data FROM records WHERE kind = ?", (kind,)).fetchall()
    return [json.loads(row["data"]) for row in rows]
