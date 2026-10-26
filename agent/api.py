"""Every call the UnderCover Agent makes to the backend, in one place."""

import os
from typing import Any, Literal

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

BACKEND_URL = os.getenv("UNDERCOVER_API", "http://localhost:8000")


class Refused(Exception):
    """The backend refused the call, and said why."""


def client() -> httpx.Client:
    """Return a client for the UnderCover backend."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30)


def request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    """Call the backend and return its reply, or raise Refused."""
    with client() as http:
        response = http.request(method, path, json=body)
    if response.is_client_error:
        raise Refused(response.json()["detail"])
    response.raise_for_status()
    return response.json()


def instructions(name: Literal["queue", "claim"]) -> str:
    """Get one of the agent's instruction documents."""
    return request("GET", f"/api/instructions/{name}")["text"]


def claims() -> list[dict[str, Any]]:
    """List the claims in the queue."""
    return request("GET", "/api/claims")


def get_claim(claim_id: str) -> dict[str, Any]:
    """Get a claim in full."""
    return request("GET", f"/api/claims/{claim_id}")


def add_step(claim_id: str, name: str, detail: str) -> None:
    """Record a step on a claim, for the handlers to watch."""
    request("POST", f"/api/claims/{claim_id}/steps", {"name": name, "detail": detail})


def start_claim(claim_id: str) -> None:
    """Start a run on a waiting claim."""
    request("POST", f"/api/claims/{claim_id}/run")


def finish_claim(claim_id: str, note: str) -> None:
    """End a claim's run, with a closing note."""
    request("POST", f"/api/claims/{claim_id}/finish", {"note": note})


def wording_sections() -> list[dict[str, str]]:
    """List the numbered sections of the policy wording."""
    return request("GET", "/api/policy-wording/sections")


def wording_section(section: str) -> dict[str, str]:
    """Get one numbered section of the policy wording."""
    return request("GET", f"/api/policy-wording/{section}")


def manual_sections() -> list[dict[str, str]]:
    """List the numbered sections of the claims manual."""
    return request("GET", "/api/manual/sections")


def manual_section(section: str) -> dict[str, str]:
    """Get one numbered section of the claims manual."""
    return request("GET", f"/api/manual/{section}")


def record_decision(
    claim_id: str,
    outcome: str,
    payout: float,
    reason: str,
    policy_section: str,
) -> None:
    """Record a claim's decision."""
    request(
        "POST",
        f"/api/claims/{claim_id}/decision",
        {
            "outcome": outcome,
            "payout": payout,
            "reason": reason,
            "policy_section": policy_section,
        },
    )


def pay_claim(claim_id: str, amount: float) -> None:
    """Pay an approved claim its payout."""
    request("POST", f"/api/claims/{claim_id}/payment", {"amount": amount})


def start_run(cap: int) -> dict[str, Any]:
    """Start a run over the waiting claims, up to the cap."""
    return request("POST", "/api/runs", {"cap": cap})


def get_run(run_id: str) -> dict[str, Any]:
    """Get a run with its to-do list."""
    return request("GET", f"/api/runs/{run_id}")


def current_run() -> dict[str, Any] | None:
    """Get the most recent run with its to-do list."""
    return request("GET", "/api/runs/current")


def set_run_item(run_id: str, claim_id: str, state: str, note: str) -> None:
    """Set where a claim has got to in a run's to-do list."""
    request(
        "POST",
        f"/api/runs/{run_id}/items/{claim_id}",
        {"state": state, "note": note},
    )


def finish_run(run_id: str, summary: str) -> None:
    """Finish a run with a summary."""
    request("POST", f"/api/runs/{run_id}/finish", {"summary": summary})
