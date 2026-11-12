"""Input guardrail — deterministic rule layer + optional LLM judge (ADR-0005)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ops_copilot.config import settings

# Patterns that indicate prompt injection / jailbreak attempts.
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier|preceding)\s+(instructions?|prompts?|rules?)",
    r"disregard\s+(all\s+)?(previous|prior|above|your)",
    r"forget\s+(everything|all\s+previous|your\s+instructions)",
    r"you\s+are\s+now\s+(a|an|in)\b",
    r"act\s+as\s+(if\s+you\s+(are|were)\s+)?(a|an)\s+(different|unrestricted|unfiltered)",
    r"pretend\s+to\s+be\b",
    r"(dan|jailbreak)\s*mode",
    r"developer\s+mode",
    r"system\s+prompt",
    r"reveal\s+(your|the)\s+(instructions?|prompt|system)",
    r"print\s+(your|the)\s+(instructions?|prompt|system\s*prompt)",
    r"show\s+me\s+your\s+(prompt|instructions)",
    r"override\s+(your\s+)?(instructions?|rules?|guardrails?|restrictions?)",
    r"bypass\s+(all\s+)?(restrictions?|filters?|guardrails?|safety)",
    r"unfiltered\s+mode",
    r"no\s+(restrictions|rules|guardrails|filters)\b",
    r"you\s+have\s+no\s+(rules|restrictions|guidelines)",
    r"execute\s+(this\s+)?(command|shell|code)",
    r"rm\s+-rf",
    r"drop\s+table",
    r"sudo\s",
    r"\bapi[_\s-]?key\b",
    r"\bpassword\b",
    r"\bsecret\b",
]
_COMPILED = [(re.compile(p, re.IGNORECASE)) for p in _INJECTION_PATTERNS]

# PII patterns — scrubbed BEFORE anything reaches the LLM or LangSmith.
# Order matters: 12-digit IDs must be tried before grouped cards, or a
# contiguous 12-digit ID gets swallowed by the card pattern.
_PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"(?:\+91[\s-]?)?[6-9]\d{9}\b"), "[PHONE]"),
    (re.compile(r"\b\d{12}\b"), "[ID]"),
    (re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}(?:\s?\d{4})?\b"), "[CARD]"),
]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class GuardVerdict:
    allowed: bool
    reason: str
    scrubbed_goal: str
    layer: str
    matched_patterns: list[str]


def scrub_pii(text: str) -> tuple[str, list[str]]:
    scrubbed = text
    found: list[str] = []
    for pattern, replacement in _PII_PATTERNS:
        if pattern.search(scrubbed):
            found.append(replacement.strip("[]"))
            scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed, found


def check_rules(goal: str) -> GuardVerdict:
    """Deterministic layer — always runs, testable offline."""
    goal = _CONTROL_CHARS.sub("", goal or "").strip()

    if not goal:
        return GuardVerdict(False, "Goal is empty", goal, "rules", [])
    if len(goal) > settings.goal_max_chars:
        return GuardVerdict(False, f"Goal exceeds {settings.goal_max_chars} characters",
                            goal[:settings.goal_max_chars], "rules", ["length"])

    matched = [p.pattern for p in _COMPILED if p.search(goal)]
    if matched:
        return GuardVerdict(
            False,
            "Goal contains prompt-injection or unsafe patterns and was blocked",
            goal, "rules", matched,
        )

    scrubbed, pii = scrub_pii(goal)
    return GuardVerdict(True, "allowed", scrubbed, "rules", pii)


async def check(goal: str) -> GuardVerdict:
    """Full guard: rules first (cheap, deterministic), then optional LLM judge."""
    verdict = check_rules(goal)
    if not verdict.allowed:
        return verdict

    if settings.guard_llm_judge and settings.llm_enabled:
        try:
            from ops_copilot.llm.client import judge_goal
            judge = await judge_goal(verdict.scrubbed_goal)
            if judge.verdict == "BLOCK":
                return GuardVerdict(
                    False, f"LLM judge blocked goal: {judge.reason or 'off-topic or unsafe'}",
                    verdict.scrubbed_goal, "rules+llm", verdict.matched_patterns,
                )
            return GuardVerdict(True, "allowed", verdict.scrubbed_goal, "rules+llm",
                               verdict.matched_patterns)
        except Exception:
            # Judge unavailable → fail open on rules-only (rules already passed)
            return verdict

    return verdict
