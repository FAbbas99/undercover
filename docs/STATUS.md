# Status

The pilot is being built from `docs/PLAN.md`. Done so far: Phases 1 to 5.

## Backend

FastAPI on SQLite. The database is `undercover.db` at the repo root (or the path in `UNDERCOVER_DB`), created and seeded on first use from named files in `data/`. It never loads `data/evals/`, `data/security/` or the claims manual. `uv run -m backend.reset` deletes it and seeds it again.

Operations:

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
- `record_decision`: `POST /api/claims/{claim_id}/decision`, approve (payout above 0), decline or refer (payout 0), once, during a run
- `pay_claim`: `POST /api/claims/{claim_id}/payment`, the approved payout exactly; refused (409) over $1,000 until signed off
- `sign_off`: `POST /api/claims/{claim_id}/sign-off`, a handler who may approve over the limit signs off and the claim is paid

Status is worked out from the record: `waiting`, `in_progress`, `awaiting_signoff` (approved over the limit, not signed off) or `decided`. Payments are recorded only; no money moves.

## Agent

`agent/main.py`: `run(claim_id, thread_id)` on LangChain's `create_agent`, with `openai/gpt-6-luna` at low reasoning effort, or `MODEL_NAME` if set. It reads its instructions from `get_instructions` and has four tools, each a call to the backend: `get_claim`, `get_policy_wording`, `record_decision` and `pay_claim`. A callback records each tool call as a step. The run always ends with `finish_run`; if the model fails, the error is the last step and the claim goes back to waiting. The backend starts it from `run_agent`.

If the backend restarts during a run, the claim stays in progress; `uv run -m backend.reset` starts the queue over.

## Dashboard

React, Vite and TypeScript in `dashboard/`, in the brand's fonts and colors, light or dark with the system setting.

- Queue (`#/`): counts for each status, a status filter, and every claim with its customer, type, summary, date, amount and status. It refreshes every two seconds.
- Claim (`#/claims/CLM-1001`):
  - a Run agent button on a waiting claim
  - the agent's steps, updated every second while it works
  - a sign-off panel when an approval over $1,000 waits: choose a handler who may approve over the limit, and the claim is paid
  - the decision with its reason and policy section, and the payment
  - the customer's story, the items, the policy and plan, the customer's earlier claims and the documents
- Agent instructions (`#/instructions`): read only.

`npm run e2e:serve` starts a separate backend on port 8001, with a fresh database and a scripted model that never calls a real one, and a dashboard on http://localhost:5174 that uses it.

## Running it

- `uv sync` and `npm install`, then `npm run dev`: backend on http://127.0.0.1:8000, dashboard on http://localhost:5173
- Run the agent on a claim: `curl -X POST http://127.0.0.1:8000/api/claims/CLM-1001/run`, then `GET /api/claims/CLM-1001`
- `npm run check`: every check
