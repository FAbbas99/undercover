# Status

The pilot is being built from `docs/PLAN.md`. Done so far: Phases 1 and 2.

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

## Agent and dashboard

Still the hello-world skeleton: `run(claim_id, thread_id)` with one tool, and a page that shows whether the backend is up.

## Running it

- `uv sync` and `npm install`, then `npm run dev`: backend on http://127.0.0.1:8000, dashboard on http://localhost:5173
- `npm run check`: every check
