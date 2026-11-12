# ADR-0008: SQLite-only storage

**Status:** Accepted (2026-11-11)

## Context

State to persist: domain data (faculty, courses, CRM, LMS state, faculty
calendar) and workflow checkpoints (LangGraph state per session). The team
explicitly chose to avoid running a database server for this project.

## Options considered

1. **SQLite everywhere** — embedded, zero-ops, WAL mode allows concurrent
   readers with a single writer.
2. **SQLite dev + Postgres prod** — realistic at scale, but requires docker
   compose services, drivers and migrations tooling the team opted out of.
3. **Postgres everywhere** — best concurrency; contradicts the decision to keep
   the stack single-binary.

## Decision

**SQLite only**, with production hygiene:

- Two database files under `data/` (gitignored):
  `ops_copilot.db` (domain data) and `checkpoints.db` (LangGraph checkpointer).
- **WAL journal mode** + `busy_timeout` on every connection.
- All writes use short transactions; the checkpointer holds one long-lived
  `aiosqlite` connection (pinned `aiosqlite==0.21.*` — 0.22 removed the
  `Connection` thread API that `langgraph-checkpoint-sqlite` calls; see
  ADR-0001 verification).
- Booking writes serialize through `BEGIN IMMEDIATE` transactions
  (ADR-0009).
- Schema changes go through an explicit, versioned migration list in
  `ops_copilot.db.migrations` (schema_version table) — no ad-hoc `CREATE
  TABLE IF NOT EXISTS` drift across modules.

## Consequences

- +: single artifact to back up; trivially runs in the container
  (ADR-0010) with a bind-mounted volume; no credentials to manage.
- −: single-writer at a time — acceptable for a control plane with
  human-in-the-loop cadence (minutes between writes), not for high-concurrency
  multi-process serving.
- Revisit trigger: if concurrent sessions routinely hit `database is locked`
  under WAL+busy_timeout, supersede this ADR with the Postgres option; the
  code is layered so only `db/` and the checkpointer factory change.
