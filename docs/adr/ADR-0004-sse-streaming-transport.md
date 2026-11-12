# ADR-0004: Server-Sent Events as the streaming transport

**Status:** Accepted (2026-11-11)

## Context

The frontend consumes a live feed of agent progress events (start/result/
plan_ready/execution/complete) while workflows run in the background. The POC
already uses SSE over `GET /stream/{session_id}` backed by a per-session
`asyncio.Queue`.

## Options considered

1. **SSE** — one-directional server→client streaming over plain HTTP; native
   `EventSource` in the browser; auto-reconnect built in.
2. **WebSockets** — bidirectional, lower per-message overhead, but requires
   connection-state management, heartbeat logic, and a different ops story
   behind proxies.
3. **Polling** — simplest, but latency and chattiness make the "live agents"
   UX worse.

## Decision

Keep **SSE**. The communication is inherently one-directional per phase
(launch → plan events; approve → execution events). Actions (launch/approve/
reject) are plain POSTs.

Changes vs the POC:

- The SSE stream is fed from the **session event bus**, which both the initial
  planning run and the post-approval resumed run publish into — one stream
  covers the whole session lifecycle (frontend no longer opens a second
  `EventSource` for execution).
- Reconnect-safe: on client reconnect the stream drains from the live queue;
  session status is also available via `GET /session/{id}`.
- Idempotent close: a `None` sentinel closes the stream exactly once.

## Consequences

- No new dependencies; works behind `uvicorn` directly (matches ADR-0010).
- If we later build interactive agent chat (user sends messages mid-run), SSE
  is insufficient and this ADR gets superseded by a WebSocket decision.
- SSE through certain proxies needs `X-Accel-Buffering: no` (already set).
