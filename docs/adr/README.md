# Architecture Decision Records

ADRs capture **why** the system is built the way it is. Each records one
significant decision: its context, the options considered, and its consequences.
ADRs are immutable once accepted — to reverse one, write a new ADR that supersedes it.

| # | Title | Status |
|---|---|---|
| [0001](ADR-0001-langgraph-interrupt-based-hitl.md) | LangGraph interrupt-based human-in-the-loop with durable checkpoints | Accepted |
| [0002](ADR-0002-langsmith-observability.md) | LangSmith for tracing and latency monitoring | Accepted |
| [0003](ADR-0003-gemini-2-5-flash-structured-output.md) | Gemini 2.5 Flash with native structured output | Accepted |
| [0004](ADR-0004-sse-streaming-transport.md) | Server-Sent Events as the streaming transport | Accepted |
| [0005](ADR-0005-guardrail-placement.md) | Guardrail placement at the LLM boundary | Accepted |
| [0006](ADR-0006-langsmith-eval-harness.md) | LangSmith datasets/evals as the LLM eval harness | Accepted |
| [0007](ADR-0007-src-layout-packaging.md) | src/ layout packaging with uv | Accepted |
| [0008](ADR-0008-sqlite-storage.md) | SQLite-only storage | Accepted |
| [0009](ADR-0009-transactional-calendar-booking.md) | Transactional calendar booking with auto-fallback ladder | Accepted |
| [0010](ADR-0010-docker-compose-deployment.md) | Docker Compose deployment | Accepted |

## Format

MADR-lite: **Status / Context / Options / Decision / Consequences**.
