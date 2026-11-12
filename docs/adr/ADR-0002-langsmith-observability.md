# ADR-0002: LangSmith for tracing and latency monitoring

**Status:** Accepted (2026-11-11)

## Context

We need per-node tracing, latency visibility, token/cost accounting, and error
rates for the agent workflow. The team explicitly does not want to adopt
self-hosted MLOps tooling (OpenTelemetry collectors, Jaeger, Prometheus,
Grafana) for this project.

## Options considered

1. **OpenTelemetry + Jaeger + Prometheus + Grafana (self-hosted)** — vendor-neutral,
   free, production-grade, but a large operational surface (4 extra services,
   instrumentation of FastAPI + LangGraph + LLM calls, dashboards to build).
2. **LangSmith (hosted SaaS)** — LangChain/LangGraph emit traces automatically
   when env vars are set; per-node latency, token usage, cost, and error dashboards
   come out of the box; no infra to run.
3. **Hybrid** — LangSmith now, OTel later.

## Decision

**LangSmith** for all observability:

- Enable via env only: `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`,
  `LANGSMITH_PROJECT`. Zero code changes for LangGraph/LangChain spans.
- LangGraph traces every node (guard, parse, faculty, ops, marketing, aggregate,
  approval, reserve, execute) with inputs/outputs, latency, and LLM token counts.
- To make latency observable **in-app** without any dashboards, we additionally
  keep a lightweight in-process metrics registry (node latency histograms,
  LLM time-to-first-token, counters) exposed at `GET /metrics` as JSON. This is
  not a replacement for tracing — it powers a "current health" view and CI checks.

## Consequences

- +: ~zero setup; best-in-class LangGraph integration; per-run debugging URLs.
- −: traces (goal text, plan content) leave the premises — acceptable for this
  POC's non-real data; flagged as a production consideration for real student data.
- −: requires an internet-reachable API and a LangSmith API key; the app degrades
  gracefully (tracing silently off) when absent.
- −: in-app `/metrics` is process-local and resets on restart — fine for a
  single-process deployment (matches ADR-0010).
- Latency SLOs: planning phase p95 ≤ 30 s (LLM included), booking p95 ≤ 2 s.
  Tracked via LangSmith dashboards and `/metrics`.
