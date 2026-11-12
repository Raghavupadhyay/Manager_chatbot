# ADR-0006: LangSmith datasets/evals as the LLM eval harness

**Status:** Accepted (2026-11-11)

## Context

We need regression coverage for: (a) intent-extraction accuracy on normal
goals, (b) guardrail behavior on adversarial inputs (jailbreak/injection/
off-topic/PII — must block), (c) operational metrics (latency, cost).
The team chose LangSmith for observability (ADR-0002); a separate eval tool
(promptfoo) would mean learning and maintaining a second platform.

## Options considered

1. **promptfoo** — excellent YAML/CI UX, but a second tool + config ecosystem.
2. **LangSmith datasets + evaluate()** — datasets and evaluators live where the
   traces already live; eval runs attach directly to traced runs.
3. **Custom pytest harness** — full control, zero deps, but we rebuild dataset
   versioning, comparison and reporting.

## Decision

**LangSmith datasets + `evaluate()`** as the primary harness:

- `evals/datasets/golden_goals.jsonl` — labeled goals → expected intent
  (drives *accuracy* metric).
- `evals/datasets/adversarial_prompts.jsonl` — jailbreak/injection/off-topic/
  PII cases with expected verdicts (drives *block-rate* metric, target 100%).
- `evals/run_evals.py` creates/updates the LangSmith datasets (stable dataset
  names; content-addressed updates) and runs the target (guard + parse path)
  against them with evaluators: exact-match on intent fields, verdict-match for
  the guard, and latency capture per example.
- CI gate: `python evals/run_evals.py --fail-on regression` exits non-zero if
  accuracy drops or any adversarial case passes the guard.

**Local deterministic fallback:** the same adversarial dataset runs as a plain
pytest suite (`tests/test_guardrails.py`) against the rule layer only — CI
never *requires* LLM keys to prove guardrail regressions. LangSmith runs add
the LLM-judge layer and accuracy numbers on machines with keys.

## Consequences

- One platform for traces, datasets, evals and dashboards.
- Eval runs are visible in LangSmith with full trace linkage per example.
- Requires `LANGSMITH_API_KEY` for the full run; rule-layer regression works
  offline (pytest) regardless.
- Datasets are code-reviewed JSONL files in-repo — versioned with the code.
