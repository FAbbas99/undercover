# Status

The pilot from `docs/PLAN.md` is built: all six phases.

## Running it

- `uv sync` and `npm install`, once.
- `npm run dev`: the backend on http://127.0.0.1:8000 and the dashboard on http://localhost:5173. The backend reloads when `backend/` or `agent/` changes.
- Open a claim and click Run agent, or with the backend running, `uv run -m agent CLM-1001`, which starts the run through the backend, prints each step and then the decision. A run calls the model, using `OPENROUTER_API_KEY` from `.env`. Set `MODEL_NAME=openrouter/free` for no cost.
- `uv run -m backend.reset`: starts the queue over, with every claim waiting.
- `npm run check`: every check, including the end-to-end tests.
- `npm run e2e:serve`: the end-to-end tests' servers, to look at by hand. The backend is on 8001 with a fresh database and a scripted model that never calls a real one, and the dashboard is on http://localhost:5174.

## Backend

FastAPI on SQLite, in `backend/`.

- **Database:** `undercover.db` at the repo root, or the path in `UNDERCOVER_DB`. It is created and seeded on first use from seven named files in `data/`. It never loads `data/evals/`, `data/security/` or the claims manual.
- **Personal data:** customers' contact details stay in the database and are not served.
- **Payments:** recorded only; no money moves.

Operations, each with an `operation_id`, a one-line docstring and no optional inputs:

- `health`: `GET /api/health`
- `list_claims`: `GET /api/claims`
- `get_claim`: `GET /api/claims/{claim_id}`, with policy, plan, add-ons, the customer's name and earlier claims, decision, payment and steps
- `get_policy_wording`: `GET /api/policy-wording`
- `get_instructions`: `GET /api/instructions`, the agent's instructions from `backend/instructions.md`
- `list_handlers`: `GET /api/handlers`
- `get_settings`: `GET /api/settings`, the $1,000 approval limit
- `run_agent`: `POST /api/claims/{claim_id}/run`, starts the agent on a waiting claim in the background (202)
- `add_step`: `POST /api/claims/{claim_id}/steps`, a step of a run in progress
- `finish_run`: `POST /api/claims/{claim_id}/finish`, ends a run; with no decision the claim goes back to waiting
- `record_decision`: `POST /api/claims/{claim_id}/decision`
  - approve with a payout above 0, or decline or refer with a payout of 0
  - once per claim, during a run
- `pay_claim`: `POST /api/claims/{claim_id}/payment`
  - the amount must be exactly the approved payout
  - over $1,000 it is refused (409) until a handler signs off
- `sign_off`: `POST /api/claims/{claim_id}/sign-off`, a handler who may approve over the limit signs off, and the claim is paid

A claim's status is worked out from its record:

| Status | When |
|---|---|
| `waiting` | no run has started |
| `in_progress` | a run is under way |
| `awaiting_signoff` | approved over the limit, not yet signed off |
| `decided` | everything else that has a decision |

## Agent

`run(claim_id, thread_id)` in `agent/main.py`, on LangChain's `create_agent`. It uses `openai/gpt-6-luna` at low reasoning effort, or `MODEL_NAME` if set.

- It reads its instructions from `get_instructions` at the start of each run.
- It has four tools, each a call to the backend: `get_claim`, `get_policy_wording`, `record_decision` and `pay_claim`.
- A callback records each tool call as a step.
- Every run ends with `finish_run`. If the model fails, the error is the last step and the claim goes back to waiting.

If the backend restarts during a run, the claim stays in progress; `uv run -m backend.reset` starts the queue over.

## Dashboard

React, Vite and TypeScript in `dashboard/`, in the brand's fonts and colors, light or dark with the system setting.

- **Queue** (`#/`): counts for each status, a status filter, and every claim with its customer, type, summary, date, amount and status. It refreshes every two seconds.
- **Claim** (`#/claims/CLM-1001`):
  - a Run agent button on a waiting claim
  - the agent's steps, updated every second while it works
  - a sign-off panel when an approval over $1,000 waits: choose a handler who may approve over the limit, and the claim is paid
  - the decision with its reason and policy section, and the payment
  - the customer's story, the items, the policy and plan, the customer's earlier claims and the documents
- **Agent instructions** (`#/instructions`): read only.

## Tests

- **pytest:** 48 tests, in `backend/tests/` and `agent/tests/`. Agent tests use a stub model against the backend in-process.
- **vitest:** 18 tests, in `dashboard/src/*.test.tsx`, with a stubbed `fetch`.
- **Playwright:** 4 tests, in `e2e/`, on their own servers (8001 and 5174) with the scripted model in `agent/tests/e2e_server.py`. They run safely while `npm run dev` is running.

No test calls a real model, and nothing opens `data/evals/`.
