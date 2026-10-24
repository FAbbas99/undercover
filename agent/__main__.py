"""Run the UnderCover Agent on one claim: `uv run -m agent CLM-1001`."""

import json
import sys
import time
from typing import Any

from agent.main import call

POLL_SECONDS = 1.0


def decide(claim_id: str) -> dict[str, Any]:
    """Start the agent on a claim through the backend, print its steps, wait."""
    started = call("POST", f"/api/claims/{claim_id}/run")
    if started.startswith("Refused"):
        raise SystemExit(started)
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


def main(args: list[str]) -> None:
    """Run the agent on the claim named in the arguments."""
    if len(args) != 1:
        raise SystemExit("Usage: uv run -m agent CLM-1001")
    print(report(decide(args[0])))


if __name__ == "__main__":
    main(sys.argv[1:])
