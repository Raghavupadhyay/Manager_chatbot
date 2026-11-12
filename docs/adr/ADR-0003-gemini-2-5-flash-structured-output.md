# ADR-0003: Gemini 2.5 Flash with native structured output

**Status:** Accepted (2026-11-11) — **supersedes the earlier "keep gemini-1.5-flash" decision**

## Context

The manager agent extracts a structured intent (`batch_type`, `subject_area`,
`timeline`, `launch_date_estimate`, `expected_duration_weeks`, `priority`) from
the free-text goal. The POC did this by prompting Gemini 1.5 Flash to "return
ONLY valid JSON" and running `json.loads` on the reply — fragile (markdown
fences, malformed JSON, hallucinated enum values) and dependent on model
availability.

During implementation verification we found **`gemini-1.5-flash` has been
retired by Google** — the API returns `404 models/gemini-1.5-flash is not found`.
The project key serves `gemini-2.5-flash` and later models. "Stay on 1.5-flash"
is therefore not executable; the decision must be superseded.

## Options considered

1. **gemini-1.5-flash** (original choice) — retired; 404s. Not viable.
2. **gemini-2.5-flash** — stable GA successor, same API surface, supports native
   structured output and JSON schemas; verified live with our key.
3. **gemini-flash-latest alias** — always current, but model behavior can shift
   under us without notice — bad for eval stability.
4. **Newest preview models (3.x)** — faster/cheaper possibly, but moving target
   and less battle-tested; unnecessary for intent extraction.

## Decision

- Default LLM: **`gemini-2.5-flash`**, `temperature=0`, configurable via
  `GOOGLE_MODEL` env (no code change needed to swap models later).
- Intent extraction uses **native structured output**:
  `llm.with_structured_output(IntentSchema)` (Gemini response schema /
  tool-constrained decoding) instead of prompt-for-JSON + `json.loads`.
- The schema is a **pydantic model** with `Literal` enums for `timeline` and
  `priority` — invalid values fail validation instead of silently flowing downstream.
- Because live testing showed the model can still return semantically loose
  values (e.g. `"next month"` in a date field, subject_area variants), the
  structured output is followed by a **normalization layer** (output guard,
  ADR-0005): canonical subject-area mapping, relative-date resolution,
  duration clamping — and a deterministic keyword fallback parser when the key
  is absent or the call fails (bounded retries with backoff + per-call timeout).

## Consequences

- Model prompt-injection surface is reduced: schema-constrained decoding
  cannot "unlock" new fields, and enum literals bound the taxonomy.
- `GOOGLE_MODEL` env makes future model swaps a config change (ADR-0003 can be
  superseded without code surgery).
- Fallback parser remains the deterministic path in CI and key-less local runs,
  so tests never depend on the LLM.
- Cost: 2.5-flash pricing differs from 1.5-flash; token spend is monitored via
  LangSmith (ADR-0002).
