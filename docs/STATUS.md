# Status

The pilot from `docs/PLAN.md` is built: all six phases.

## Running it

- `uv sync` and `npm install`, once.
- `npm run dev`: the backend on http://127.0.0.1:8000 and the dashboard on http://localhost:5173. The backend reloads when `backend/` or `agent/` changes.
- Open a claim and click Run agent. Or, with the backend running:
  - `uv run -m agent`: works through every waiting claim, one at a time, printing each one's steps and decision, then a summary. Claims that are not waiting are skipped, and a claim the backend refuses to start is reported and the batch carries on. A full queue is 25 model calls.
  - `uv run -m agent CLM-1001`: one claim. A run calls the model, using `OPENROUTER_API_KEY` from `.env`. Set `MODEL_NAME=openrouter/free` for no cost.
- `uv run -m backend.reset`: starts the queue over, with every claim waiting.
- `npm run check`: every check, including the end-to-end tests.
- `npm run e2e:serve`: the end-to-end tests' servers, to look at by hand. The backend is on 8001 with a fresh database and a scripted model that never calls a real one, and the dashboard is on http://localhost:5174.

## Backend

FastAPI on SQLite, in `backend/`.

- **Database:** `undercover.db` at the repo root, or the path in `UNDERCOVER_DB`. It is created and seeded on first use from eight named files in `data/`. It never loads `data/evals/` or `data/security/`.
- **Personal data:** customers' contact details stay in the database and are not served.
- **Payments:** recorded only; no money moves.

Operations, each with an `operation_id`, a one-line docstring and no optional inputs:

- `health`: `GET /api/health`
- `list_claims`: `GET /api/claims`
- `get_claim`: `GET /api/claims/{claim_id}`, with policy, plan, add-ons, the customer's name and earlier claims, decision, payment and steps
- `list_wording_sections`: `GET /api/policy-wording/sections`, the numbered sections of the policy wording
- `get_wording_section`: `GET /api/policy-wording/{section}`, one section, with its text
- `list_manual_sections`: `GET /api/manual/sections`, the numbered sections of the claims manual
- `get_manual_section`: `GET /api/manual/{section}`, one section, with its text
- `get_queue_instructions`: `GET /api/instructions/queue`, from `backend/instructions_queue.md`
- `get_claim_instructions`: `GET /api/instructions/claim`, from `backend/instructions_claim.md`
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
- `start_run`: `POST /api/runs`, starts a run over the waiting claims, up to the cap (202)
- `get_current_run`: `GET /api/runs/current`, the most recent run with its to-do list, or null
- `get_run`: `GET /api/runs/{run_id}`, one run with its to-do list
- `set_run_item`: `POST /api/runs/{run_id}/items/{claim_id}`, an item's state and note
- `finish_queue_run`: `POST /api/runs/{run_id}/finish`, the run's summary; refused while an item is still to do or is done on a claim with no decision

A claim that ends a run with no decision counts a failure. A claim that has failed twice is not taken into a run again and waits for a handler.

A claim's status is worked out from its record:

| Status | When |
|---|---|
| `waiting` | no run has started |
| `in_progress` | a run is under way |
| `awaiting_signoff` | approved over the limit, not yet signed off |
| `decided` | everything else that has a decision |

## Runs

A run is one pass over the queue. The backend takes the lowest-numbered waiting claims up to the cap, and the agent works them, keeping a to-do list of `to_do`, `in_progress`, `done` and `left_for_handler` items. The queue page shows it. One run at a time: a run left unfinished by a restart is closed, and its claims go back to waiting, when the next run starts.

## Agent

`run(claim_id, thread_id)` in `agent/main.py`, on LangChain's `create_agent`. It uses `openai/gpt-6-luna` at low reasoning effort, or `MODEL_NAME` if set.

- It reads its instructions from `get_claim_instructions` at the start of each run.
- Its tools are calls to the backend: `get_claim`, `list_wording_sections`, `get_wording_section`, `list_manual_sections`, `get_manual_section`, `record_decision` and `pay_claim`. It never receives a whole document.
- A callback records each tool call as a step.
- Every run ends with `finish_run`. If the model fails, the error is the last step and the claim goes back to waiting.

If the backend restarts during a run, the claim stays in progress; `uv run -m backend.reset` starts the queue over.

## Dashboard

React, Vite and TypeScript in `dashboard/`, in the brand's fonts and colors, light or dark with the system setting.

- **Queue** (`#/`): counts for each status, a status filter, and every claim with its customer, type, summary, date, amount claimed, status, decision and payout. It refreshes every two seconds.
- **Claim** (`#/claims/CLM-1001`):
  - a Run agent button on a waiting claim
  - the agent's steps, updated every second while it works
  - a sign-off panel when an approval over $1,000 waits: choose a handler who may approve over the limit, and the claim is paid
  - the decision with its reason and policy section, and the payment
  - the customer's story, the items, the policy and plan, the customer's earlier claims and the documents
- **Agent instructions** (`#/instructions`): read only.

## Tests

- **pytest:** 54 tests, in `backend/tests/` and `agent/tests/`. Agent tests use a stub model against the backend in-process.
- **vitest:** 19 tests, in `dashboard/src/*.test.tsx`, with a stubbed `fetch`.
- **Playwright:** 4 tests, in `e2e/`, on their own servers (8001 and 5174) with the scripted model in `agent/tests/e2e_server.py`. They run safely while `npm run dev` is running.

No test calls a real model, and nothing opens `data/evals/`.
