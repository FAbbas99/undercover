# Status

The pilot is being built from `docs/PLAN.md`. Done so far: Phase 1.

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

## Agent and dashboard

Still the hello-world skeleton: `run(claim_id, thread_id)` with one tool, and a page that shows whether the backend is up.

## Running it

- `uv sync` and `npm install`, then `npm run dev`: backend on http://127.0.0.1:8000, dashboard on http://localhost:5173
- `npm run check`: every check
