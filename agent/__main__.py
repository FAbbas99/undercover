"""Run the UnderCover Agent from the command line.

`uv run -m agent` works through every waiting claim, one at a time.
`uv run -m agent CLM-1001` runs it on one claim.
"""

import json
import sys
import time
from collections import Counter
from typing import Any

from agent.main import call

POLL_SECONDS = 1.0
USAGE = "Usage: uv run -m agent [CLM-1001]"


def waiting_claims() -> list[str]:
    """Return the ids of the claims waiting in the queue."""
    claims = json.loads(call("GET", "/api/claims"))
    return [c["claim_id"] for c in claims if c["status"] == "waiting"]


def decide(claim_id: str) -> dict[str, Any] | None:
    """Start the agent on a claim through the backend, print its steps, wait.

    Returns None, after saying why, if the backend refuses to start the run.
    """
    started = call("POST", f"/api/claims/{claim_id}/run")
    if started.startswith("Refused"):
        print(started)
        return None
    seen = 0
    while True:
        claim = json.loads(call("GET", f"/api/claims/{claim_id}"))
        for step in claim["steps"][seen:]:
            print(f"{step['at'][11:19]}  {step['name']}")
        seen = len(claim["steps"])
        if claim["status"] != "in_progress":
            return claim
        time.sleep(POLL_SECONDS)


def report(claim: dict[str, Any]) -> str:
    """Describe where a claim ended up."""
    decision = claim["decision"]
    if decision is None:
        return f"No decision. {claim['steps'][-1]['detail']}"
    lines = [
        f"{decision['outcome'].capitalize()}: ${decision['payout']:,.2f}",
        f"Section: {decision['policy_section']}",
        f"Reason: {decision['reason']}",
        f"Status: {claim['status']}",
    ]
    if claim["payment"]:
        lines.append(f"Paid: ${claim['payment']['amount']:,.2f}")
    return "\n".join(lines)


def summary(claims: list[dict[str, Any]], refused: int) -> str:
    """Total up a batch: one line per claim, then counts by status."""
    lines = []
    for claim in claims:
        decision = claim["decision"]
        outcome = decision["outcome"] if decision else "no decision"
        payout = f"${decision['payout']:,.2f}" if decision else ""
        lines.append(
            f"{claim['claim_id']}  {outcome:<11}  {payout:>10}  {claim['status']}"
        )
    counts = Counter(claim["status"] for claim in claims)
    totals = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
    lines.append(f"Ran {len(claims)} claims: {totals or 'none'}")
    if refused:
        lines.append(f"Refused to start: {refused}")
    return "\n".join(lines)


def run_all() -> None:
    """Run the agent on every waiting claim, one at a time."""
    claim_ids = waiting_claims()
    if not claim_ids:
        print("No claims are waiting.")
        return
    print(f"{len(claim_ids)} claims are waiting.")
    done = []
    for claim_id in claim_ids:
        print(f"\n{claim_id}")
        claim = decide(claim_id)
        if claim:
            print(report(claim))
            done.append(claim)
    print()
    print(summary(done, len(claim_ids) - len(done)))


def main(args: list[str]) -> None:
    """Run the agent on the claim named in the arguments, or on every waiting one."""
    if len(args) > 1:
        raise SystemExit(USAGE)
    if not args:
        run_all()
        return
    claim = decide(args[0])
    if claim is None:
        raise SystemExit(1)
    print(report(claim))


if __name__ == "__main__":
    main(sys.argv[1:])
