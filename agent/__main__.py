"""Run the UnderCover Agent from the command line.

`uv run -m agent` starts a run over every waiting claim.
`uv run -m agent --cap 5` starts a run over five of them, for a trial.
`uv run -m agent CLM-1001` runs the agent on one claim.
"""

import sys
import time
from typing import Any

from agent import api

POLL_SECONDS = 1.0
USAGE = "Usage: uv run -m agent [--cap N | CLM-1001]"


def waiting() -> list[dict[str, Any]]:
    """Return the claims waiting in the queue."""
    return [claim for claim in api.claims() if claim["status"] == "waiting"]


def decide(claim_id: str) -> dict[str, Any] | None:
    """Run the agent on one claim, printing its steps as they arrive.

    Returns None, after saying why, if the backend refuses to start the run.
    """
    try:
        api.start_claim(claim_id)
    except api.Refused as refused:
        print(f"Refused: {refused}")
        return None
    seen = 0
    while True:
        claim = api.get_claim(claim_id)
        for step in claim["steps"][seen:]:
            print(f"{step['at'][11:19]}  {step['name']}  {step['detail']}")
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


def follow(run_id: str) -> dict[str, Any]:
    """Print the to-do list as it changes, until the run has finished."""
    seen: dict[str, tuple[str, str]] = {}
    while True:
        run = api.get_run(run_id)
        for item in run["items"]:
            state = (item["state"], item["note"])
            if seen.get(item["claim_id"]) != state:
                seen[item["claim_id"]] = state
                print(f"{item['claim_id']}  {item['state']:<17} {item['note']}")
        if run["finished_at"] is not None:
            return run
        time.sleep(POLL_SECONDS)


def run_the_queue(cap: int) -> None:
    """Start a run and follow it."""
    try:
        run = api.start_run(cap)
    except api.Refused as refused:
        print(f"Refused: {refused}")
        return
    print(f"Run started over {len(run['items'])} claims.")
    finished = follow(run["run_id"])
    print(f"\n{finished['summary']}")


def main(args: list[str]) -> None:
    """Start a run, or run the agent on the claim named in the arguments."""
    if not args:
        run_the_queue(len(waiting()))
        return
    if args[0] == "--cap" and len(args[1:]) == 1 and args[1].isdigit():
        run_the_queue(int(args[1]))
        return
    if len(args) == 1 and args[0].startswith("CLM-"):
        claim = decide(args[0])
        if claim is None:
            raise SystemExit(1)
        print(report(claim))
        return
    raise SystemExit(USAGE)


if __name__ == "__main__":
    main(sys.argv[1:])
