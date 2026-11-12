# ADR-0010: Docker Compose deployment

**Status:** Accepted (2026-11-11)

## Context

The repo contained an empty Dockerfile. Deployment must be reproducible with
one command, and the observability stack is SaaS (ADR-0002), storage is
embedded SQLite (ADR-0008), so no sidecar services are required.

## Options considered

1. **Docker Compose (single service)** — one command brings the whole app up.
2. **Kubernetes + Helm** — premature for a single-process control plane; no
   horizontal scaling requirement; large maintenance surface.

## Decision

**Docker Compose** with a single `app` service:

- Multi-stage `Dockerfile` (builder installs deps via `uv`, slim runtime
  copies the installed venv + source).
- `docker-compose.yml`: app on port 8000, `data/` bind-mounted volume for the
  two SQLite files (survives `docker compose down`), env vars passed through
  (`GOOGLE_API_KEY`, `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`,
  `LANGSMITH_PROJECT`, `GOOGLE_MODEL`).
- Healthcheck on `GET /health`.
- `.dockerignore` excludes `.venv`, `data/`, `.git`, docs, tests.
- A `.env.example` documents every supported variable.

## Consequences

- +: `docker compose up --build` is the entire production story for this scope.
- +: SQLite durability via the volume mount.
- −: single process — restarts drop in-flight SSE connections (clients
  reconnect; sessions themselves are durable via ADR-0001/0008).
- −: scaling out would require moving storage (supersedes ADR-0008) and
  adding an ingress — explicitly out of scope.
