# ADR-0001: LangGraph interrupt-based human-in-the-loop with durable checkpoints

**Status:** Accepted (2026-11-11)

## Context

The POC pauses agent execution so a human can review and approve the launch plan
before anything is executed. The current implementation does this with a custom
mechanism: the graph runs to completion, the final plan is parked in an in-memory
dict (`session_plans`), and a separate `/approve` endpoint triggers a disconnected
"simulate_execution" function. Consequences of that design:

- Workflow state lives only in process memory — a restart between plan-ready and
  approval loses the session entirely.
- The "execution phase" is not part of the graph; it cannot see graph state
  (faculty shortlist, intent, ops results) without ad-hoc plumbing.
- There is no single source of truth for "where is this session right now?"
- Approval is not idempotent and never performs real calendar booking
  (the booking variant of `/approve` is dead code — FastAPI first-match wins).

We are rebuilding this as a production-grade control plane, so the approval
checkpoint must be durable, resumable, and auditable.

## Options considered

1. **Keep the custom queue + dict approach** — smallest change, keeps all known
   weaknesses; in-memory only; execution lives outside the graph.
2. **Celery/RQ-style task queue with states in the app DB** — heavy for a
   single-service control plane; duplicates what LangGraph already provides.
3. **LangGraph `interrupt()` primitive with a checkpointer** — pause/resume is a
   first-class graph feature; state is serialized to storage by LangGraph;
   resuming with `Command(resume=...)` continues the same graph run.

## Decision

Use **LangGraph's `interrupt()` primitive** for the human approval checkpoint,
with an **AsyncSqliteSaver checkpointer** keyed by `thread_id = session_id`:

- The graph runs `guard_in → parse_goal → faculty → operations → marketing →
  aggregate → human_approval → (approved ? reserve → notify → execute : reject)`.
- `human_approval` calls `interrupt(plan)`; LangGraph persists the full state and
  the run pauses. `POST /approve` resumes with `Command(resume={"approved": true})`,
  `POST /reject` resumes with `{"approved": false}`.
- Everything after the interrupt executes *inside* the graph with full state access.

Verification performed (scratch environment, langgraph 0.2.60 +
langgraph-checkpoint-sqlite 2.0.11 + aiosqlite 0.21.0): pause at interrupt,
durable resume, independent threads, no state loss between runs.

**Auto-approval considered and deferred:** high-readiness plans (e.g. score ≥ 85
with a confirmed primary faculty) *could* skip the human click. We keep every
plan human-approved for now; the threshold hook is documented in ADR-0009's
consequences and can be enabled later without a graph redesign.

## Consequences

- Workflow state survives server restarts between plan and approval (durable).
- One resumable artifact per session — audit trail for "what did the human approve".
- Approval is idempotent: resuming an already-resumed thread is a no-op at the
  LangGraph level; the API layer additionally guards double-POST.
- We must hold one SQLite connection for the checkpointer (see ADR-0008) and pin
  `aiosqlite==0.21.*` (0.22 removed the `Connection` thread API the saver relies on).
- Frontend still sees the same "plan_ready → approve → execution log" flow; only
  the backend semantics change.
