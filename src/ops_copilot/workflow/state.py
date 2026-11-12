"""Workflow state — the shared channels flowing through the graph."""
from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    session_id: str
    goal: str
    guard_verdict: dict | None        # {allowed, reason, scrubbed_goal, layer}
    parsed_intent: dict | None
    faculty_result: dict | None
    ops_result: dict | None
    marketing_result: dict | None
    final_plan: dict | None
    approval: dict | None             # {"approved": bool} — resume value
    booking_result: dict | None
    notification_result: dict | None
    execution_result: dict | None
    error: str | None
