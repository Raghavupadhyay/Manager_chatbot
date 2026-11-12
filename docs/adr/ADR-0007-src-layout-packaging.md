# ADR-0007: src/ layout packaging with uv

**Status:** Accepted (2026-11-11)

## Context

The POC keeps Python modules in `backend/` with no `__init__.py` files; every
module does `sys.path.insert(0, ...)` hacks to import siblings. The duplicate
`POST /approve` route bug (ADR-0009 context) and scattered imports made the
code hard to reason about and untestable as a package. The project already
uses `uv` (`uv.lock`, README quickstart).

## Options considered

1. Keep flat `backend/` + sys.path hacks.
2. `src/` layout with a proper installed package (`uv` + `pyproject.toml`).
3. Full monorepo with separate `api`/`workers` packages — premature.

## Decision

Adopt **src-layout packaging** under `src/ops_copilot/`:

```
src/ops_copilot/
├── __init__.py, __main__.py     # python -m ops_copilot starts the server
├── config.py                    # centralized settings (env-driven)
├── api/                          # FastAPI app, routes, schemas
├── workflow/                     # graph, nodes, state, event bus
├── agents/                       # manager/faculty/operations/marketing
├── guardrails/                   # input/output guards
├── tools/                        # faculty/calendar/notification/lms/crm
├── db/                           # schema, seed, connections
├── llm/                          # model client, structured output, retries
├── observability/                # langsmith wiring, metrics registry
└── evals/                        # dataset loading helpers
```

- `pyproject.toml` with hatchling build; `uv run` installs the package into
  `.venv` from the lockfile.
- `requirements.txt` is kept **in sync** as a convenience mirror (README flow).
- Entry points: `uv run python -m ops_copilot`, `uvicorn ops_copilot.api.app:app`,
  or the root `main.py` shim for backwards familiarity.
- `ruff` configured in `pyproject.toml` as the lint/format gate.
- `.venv/`, `data/` (SQLite DBs), `__pycache__` excluded from git and Docker.

## Consequences

- All imports are absolute (`ops_copilot.tools.calendar_tool`) — no sys.path
  hacks anywhere; testable with `pytest` out of the box.
- One canonical place per concern; the dead duplicate route is deleted, not
  migrated.
- Old `backend/` directory is removed (git history preserves it).
