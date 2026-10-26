# Tech stack

- `backend/`: FastAPI and SQLite. Every API operation has an `operation_id`, a one-line docstring and no optional inputs. Paying a claim is a separate operation that takes the amount. The policy wording and the claims manual are served by numbered section, never whole.
- `agent/`: LangChain's `create_agent` on OpenRouter, in three parts: `api.py`, every call to the backend with the base URL in one place; `tools.py`, every tool, each taking its claim or run from a `ToolRuntime` context; and `harness.py`, which builds the two agents. `run_claim(claim_id, thread_id)` decides one claim and `run_queue(run_id)` works a run. It reaches claims, runs and its instructions only through the backend's API. It uses `deepseek/deepseek-v4.1-flash` with low reasoning effort by default, or the model in the environment variable `MODEL_NAME` if set, such as `openrouter/free`.
- `dashboard/`: React, Vite and TypeScript.
- `e2e/`: Playwright tests.
- `data/`: the business data the backend starts from, including the claims manual, which decisions follow. The agent never sees `data/evals/`, which holds the answer key.

Python 3.12 with uv, all in the root `pyproject.toml`. Node 26. The OpenRouter key is `OPENROUTER_API_KEY` in `.env`.
