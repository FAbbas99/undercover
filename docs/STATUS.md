# Status

The pilot from `docs/PLAN.md` and the harness from `docs/PLAN_HARNESS.md` are built: all six phases of each.

## Running it

- `uv sync` and `npm install`, once.
- `npm run dev`: the backend on http://127.0.0.1:8000 and the dashboard on http://localhost:5173. The backend reloads when `backend/` or `agent/` changes.
- Start a run from the queue page, or from the command line with the backend running:
  - `uv run -m agent`: starts a run over every waiting claim. The agent works the run's to-do list, handing each claim to a fresh worker, and ends with a summary. A full queue of 25 claims is about 25 workers' worth of model calls.
  - `uv run -m agent --cap 5`: the same, over five claims, for a trial. The rest stay waiting.
  - `uv run -m agent CLM-1001`: one claim, printing its steps and decision. A run calls the model, using `OPENROUTER_API_KEY` from `.env`. Set `MODEL_NAME=openrouter/free` for no cost.
- `uv run -m backend.reset`: starts the queue over, with every claim waiting.
- `npm run check`: every check, including the end-to-end tests.
- `npm run e2e:serve`: the end-to-end tests' servers, to look at by hand. The backend is on 8001 with a fresh database and scripted models that never call a real one, and the dashboard is on http://localhost:5174.

## Backend

FastAPI on SQLite, in `backend/`.

- **Database:** `undercover.db` at the repo root, or the path in `UNDERCOVER_DB`. It is created and seeded on first use from eight named files in `data/`, and a database from an earlier build gains the new tables and column when it is next opened. It never loads `data/evals/` or `data/security/`.
- **Documents:** the policy wording and the claims manual are split into their numbered sections by `backend/documents.py` and served a section at a time. The agent never receives a whole document.
- **Personal data:** customers' contact details stay in the database and are not served.
- **Payments:** recorded only; no money moves.

Operations, each with an `operation_id`, a one-line docstring and no optional inputs:

- `health`: `GET /api/health`
- `list_claims`: `GET /api/claims`
- `get_claim`: `GET /api/claims/{claim_id}`, with policy, plan, add-ons, the customer's name and earlier claims, decision, payment, steps and the failure count
- `list_wording_sections`: `GET /api/policy-wording/sections`, the numbered sections of the policy wording
- `get_wording_section`: `GET /api/policy-wording/{section}`, one section, with its text
- `list_manual_sections`: `GET /api/manual/sections`, the numbered sections of the claims manual
- `get_manual_section`: `GET /api/manual/{section}`, one section, with its text
- `get_queue_instructions`: `GET /api/instructions/queue`, from `backend/instructions_queue.md`
- `get_claim_instructions`: `GET /api/instructions/claim`, from `backend/instructions_claim.md`
- `list_handlers`: `GET /api/handlers`
- `get_settings`: `GET /api/settings`, the $1,000 approval limit
- `run_agent`: `POST /api/claims/{claim_id}/run`, starts a worker on a waiting claim in the background (202)
- `add_step`: `POST /api/claims/{claim_id}/steps`, a step of a run in progress
- `finish_run`: `POST /api/claims/{claim_id}/finish`, ends a run; with no decision the claim goes back to waiting and its failure count goes up
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
- `finish_queue_run`: `POST /api/runs/{run_id}/finish`, the run's summary; refused (409) while an item is still to do or is done on a claim with no decision

A claim's status is worked out from its record:

| Status | When |
|---|---|
| `waiting` | no run has started |
| `in_progress` | a run is under way |
| `awaiting_signoff` | approved over the limit, not yet signed off |
| `decided` | everything else that has a decision |

## Runs

A run is one pass over the queue.

- The backend takes the lowest-numbered waiting claims up to the cap and gives each one an item: `to_do`, `in_progress`, `done` or `left_for_handler`. The rest of the queue stays waiting.
- The agent chooses the order it works them in, and keeps the list up to date, so the handlers can watch.
- One run at a time. A run left unfinished by a restart is closed, and its claims go back to waiting, when the next run starts.
- A claim that ends a run with no decision counts a failure. After two failures it is not taken into a run again and waits for a handler, who can still run it by hand from its claim page.
- No claim is decided or paid twice: the backend refuses the second attempt.

## Agent

Two agents on one harness, both LangChain's `create_agent`, in `agent/`:

- `api.py`: every call to the backend, in one place, with the base URL in `BACKEND_URL`.
- `tools.py`: every tool. Each takes its claim or run from a `ToolRuntime` context, so the model never carries an id, and each records its own step.
- `harness.py`: the harness. `run_claim(claim_id, thread_id)` decides one claim and `run_queue(run_id)` works a run. It uses `deepseek/deepseek-v4.1-flash` at low reasoning effort, or `MODEL_NAME` if set.

The worker reads its instructions from `get_claim_instructions`, and its tools are `get_claim`, `list_wording_sections`, `get_wording_section`, `list_manual_sections`, `get_manual_section`, `record_decision` and `pay_claim`. The runner reads `get_queue_instructions`, and its tools are `get_run`, `work_claim`, `set_run_item` and `finish_queue_run`; `work_claim` hands a claim to a fresh worker and waits for its one-line answer, so the runner's context holds a line per claim rather than a claim's worth of reading.

A worker's run always ends with `finish_run`: the model's answer, an error, or `CLAIM_TIMEOUT_SECONDS` (120 by default). The model client retries a rate-limited call for about a minute before giving up. A claim is never left in progress by a worker that fails.

## Dashboard

React, Vite and TypeScript in `dashboard/`, in the brand's fonts and colors, light or dark with the system setting.

- **Queue** (`#/`):
  - the run panel: a cap, a Start run button, the current run's to-do list with each claim's state, and the summary the run ended with
  - counts for each status, a status filter, and every claim with its customer, type, summary, date, amount claimed, status, decision and payout, and its failed attempts
  - it refreshes every two seconds
- **Claim** (`#/claims/CLM-1001`):
  - a Run agent button on a waiting claim
  - the agent's steps, updated every second while it works, including the sections of the wording and the manual it read
  - a sign-off panel when an approval over $1,000 waits: choose a handler who may approve over the limit, and the claim is paid
  - the decision with its reason and policy section, and the payment
  - the customer's story, the items, the policy and plan, the customer's earlier claims and the documents
- **Agent instructions** (`#/instructions`): both documents, read only.

## Tests

- **pytest:** 96 tests, in `backend/tests/` and `agent/tests/`. The agent tests use stub models against the backend in-process, with no model called.
- **vitest:** 27 tests, in `dashboard/src/*.test.tsx`, with a stubbed `fetch`.
- **Playwright:** 5 tests, in `e2e/`, on their own servers (8001 and 5174) with the scripted models in `agent/tests/e2e_server.py`. They run safely while `npm run dev` is running.

No test calls a real model, and nothing opens `data/evals/`.
