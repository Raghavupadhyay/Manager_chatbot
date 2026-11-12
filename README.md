# Operations Copilot

Multi-agent course-launch control plane with **durable human-in-the-loop approval**, guardrails, observability, and LLM evals.

A manager goal ("Launch SSC Foundation Batch next month") flows through a guardrail, LLM intent parsing, three domain agents (Faculty, Operations, Marketing), plan aggregation — then **pauses durably** until a human approves or rejects. Approval triggers transactional calendar booking with automatic fallback, notifications, and task execution. Every step streams live to the browser over SSE.

## Architecture

```
┌────────────┐    POST /launch      ┌──────────────────────────────────────────┐
│  Browser   │ ───────────────────▶ │  FastAPI                                  │
│  (vanilla  │                      │  ├─ rate limiter · idempotency · API key   │
│  JS + SSE) │◀──────────────────── │  └─ TaskRegistry (async, one per session) │
└────────────┘   GET /stream/{sid}  └───────────────┬──────────────────────────┘
         SSE events (token/result/blocked/             │
         awaiting_approval/booking_diff/complete)      ▼
                                                ┌───────────────────────────────┐
                                                │ LangGraph (checkpointed in    │
                                                │ SQLite — AsyncSqliteSaver)    │
                                                │                               │
                                                │ guard_in ─▶ parse_goal        │
                                                │     │        (Gemini          │
                                                │     │         structured     │
                                                │  blocked      output or      │
                                                │     ▼         fallback)      │
                                                │  faculty ─▶ operations ─▶    │
                                                │  marketing ─▶ aggregate       │
                                                │     │                        │
                                                │     ▼                        │
                                                │ human_approval ── interrupt()│
                                                │     │           durable pause│
                                                │  approved? ──┬─ reject ─▶ END│
                                                │              ▼              │
                                                │ reserve_calendar (atomic    │
                                                │  booking + fallback ladder) │
                                                │     ▼                        │
                                                │  notify ─▶ execute ─▶ END    │
                                                └───────────────────────────────┘
```

- **Durable HITL** — `interrupt()` + SQLite checkpointer: pause the process, restart it, resume with `Command(resume=...)` (ADR-0001)
- **Transactional booking** — `BEGIN IMMEDIATE`, TOCTOU re-check inside the transaction, idempotent per session, PK backstop, ranked-candidate fallback ladder with date shifts, escalation when exhausted (ADR-0009)
- **Guardrails** — 4 layers: rate-limit/auth edge → deterministic injection/jailbreak regexes + PII scrubbing → schema-constrained LLM judge → pydantic output validation with canonicalization (ADR-0005)
- **LLM** — Gemini 2.5 Flash native structured output (`IntentSchema`), date-grounded prompts, retries/timeout, token streaming; deterministic keyword fallback when no key (ADR-0003)
- **Observability** — LangSmith tracing (opt-in) + in-process latency histograms (p50/p95 per node) at `GET /metrics` (ADR-0002)
- **Evals** — golden-goal + adversarial datasets, LangSmith-hosted runner with regression gate, offline pytest gate (ADR-0006)

Decisions are documented in [docs/adr/](docs/adr/README.md) (ADR-0001 … 0010).

## Layout

```
src/ops_copilot/
  api/            FastAPI app, routes (launch/stream/approve/reject), task registry
  workflow/       LangGraph assembly, nodes, state, SSE event bus
  agents/         manager (parse+plan), faculty, operations, marketing
  tools/          calendar (atomic booking), faculty, notification, LMS, CRM
  guardrails/     input guard (rules + LLM judge + PII scrub)
  llm/            Gemini client (structured output, judge, retry)
  observability/  metrics registry
  db/             SQLite migrations + seeds (domain + checkpoint DBs)
evals/            datasets (golden goals, adversarial) + LangSmith runner
tests/            guardrails, booking, workflow (interrupt/resume), API, plan
frontend/         vanilla JS single-page UI
scripts/          smoke_test.sh (live end-to-end)
```

## Quickstart

```bash
# deps (Python 3.12+)
uv sync

# configure
cp .env.example .env       # add GOOGLE_API_KEY (optional — fallback parser works without)

# run
uv run python -m ops_copilot
# → http://localhost:8000
```

## Testing

```bash
uv run pytest                    # offline suite: 74 tests (no API key needed)
uv run ruff check .              # lint
bash scripts/smoke_test.sh       # live E2E: launch → pause → approve → booked
```

## Evals

```bash
# offline CI gate (subset of LangSmith datasets, deterministic)
uv run pytest tests/test_guardrails.py

# hosted evals — requires LANGSMITH_API_KEY (+ GOOGLE_API_KEY for judge layers)
uv run python evals/run_evals.py --fail-on regression
```

Targets: guard component (block/allow/scrub correctness) and intent extraction (subject_area/timeline accuracy), with per-call latency. Gate fails on block-rate < 100%, PII scrub-rate < 100%, or intent accuracy < 90%.

## API

| Endpoint | Purpose |
|---|---|
| `POST /launch` | Start workflow (rate-limited, idempotent via `request_id`) |
| `GET /stream/{sid}` | SSE — whole session lifecycle, heartbeats, single close |
| `POST /approve/{sid}` | Resume from durable pause (idempotent) |
| `POST /reject/{sid}` | Reject plan — no bookings made |
| `GET /session/{sid}` | Phase: planning / awaiting_approval / executing / completed / rejected / escalated / blocked / failed |
| `GET /plan/{sid}` | Aggregated plan with booking candidates |
| `GET /metrics` | Node latencies (p50/p95), counters, runtime |
| `GET /faculty` `/courses` `/calendar/{id}` | Domain data for the UI |

## Docker

```bash
docker compose up --build   # app on :8000, SQLite on a named volume, healthcheck on /health
```

## Production notes

Single-process SQLite design (ADR-0008): WAL + busy_timeout, two databases (domain, checkpoints). Booking is race-safe via `BEGIN IMMEDIATE` + unique PK. Scale path: swap tools for real Google Calendar/LMS/CRM APIs, checkpointer for Postgres, and run workers behind the same DB — the graph state and phase logic are storage-agnostic.
