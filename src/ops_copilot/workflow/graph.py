"""LangGraph assembly — durable HITL workflow (ADR-0001).

Planning order is unchanged from the POC (parse → faculty → ops → marketing →
aggregate); the execution half is rebuilt as real graph nodes behind a durable
interrupt. run/resume helpers + session status derive from the checkpointer —
the checkpoint state is the single source of truth.
"""
from __future__ import annotations

import asyncio
import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from ops_copilot.config import settings
from ops_copilot.observability.metrics import metrics
from ops_copilot.workflow import nodes
from ops_copilot.workflow.events import bus
from ops_copilot.workflow.state import AgentState

log = logging.getLogger("ops_copilot.graph")


def build_graph(checkpointer: BaseCheckpointSaver):
    g = StateGraph(AgentState)

    g.add_node("guard_in", nodes.guard_in_node)
    g.add_node("parse_goal", nodes.parse_goal_node)
    g.add_node("faculty", nodes.faculty_node)
    g.add_node("operations", nodes.operations_node)
    g.add_node("marketing", nodes.marketing_node)
    g.add_node("aggregate", nodes.aggregate_node)
    g.add_node("human_approval", nodes.human_approval_node)
    g.add_node("reserve_calendar", nodes.reserve_calendar_node)
    g.add_node("notify", nodes.notify_node)
    g.add_node("execute", nodes.execute_node)
    g.add_node("reject", nodes.reject_node)

    g.add_edge(START, "guard_in")

    def route_after_guard(state: AgentState) -> str:
        return "parse_goal" if state.get("guard_verdict", {}).get("allowed") else END

    g.add_conditional_edges("guard_in", route_after_guard, ["parse_goal", END])

    g.add_edge("parse_goal", "faculty")
    g.add_edge("faculty", "operations")
    g.add_edge("operations", "marketing")
    g.add_edge("marketing", "aggregate")
    g.add_edge("aggregate", "human_approval")

    def route_after_approval(state: AgentState) -> str:
        return "reserve_calendar" if state.get("approval", {}).get("approved") else "reject"

    g.add_conditional_edges("human_approval", route_after_approval, ["reserve_calendar", "reject"])

    g.add_edge("reserve_calendar", "notify")
    g.add_edge("notify", "execute")
    g.add_edge("execute", END)
    g.add_edge("reject", END)

    return g.compile(checkpointer=checkpointer)


# ── Public helpers ────────────────────────────────────────────────────────────

def config_for(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _initial_state(session_id: str, goal: str) -> dict:
    return {
        "session_id": session_id, "goal": goal,
        "guard_verdict": None, "parsed_intent": None, "faculty_result": None,
        "ops_result": None, "marketing_result": None, "final_plan": None,
        "approval": None, "booking_result": None, "notification_result": None,
        "execution_result": None, "error": None,
    }


async def run_workflow(graph, session_id: str, goal: str) -> None:
    """Planning phase: guard → parse → agents → aggregate → durable pause."""
    sid = session_id
    metrics.inc("sessions_started")
    try:
        await asyncio.wait_for(
            graph.ainvoke(_initial_state(sid, goal), config_for(sid)),
            timeout=settings.planning_timeout_s,
        )
        # Terminal without execute/reject (guard blocked, or END reached
        # another way) → close the SSE stream so the client isn't left hanging.
        snap = await graph.aget_state(config_for(sid))
        if not (snap.next or ()):
            await bus.close(sid)
    except asyncio.TimeoutError:
        metrics.inc("errors")
        await bus.emit(sid, "system", "error",
                       f"Planning timed out after {settings.planning_timeout_s:.0f}s")
        await bus.close(sid)
    except Exception as e:  # noqa: BLE001
        metrics.inc("errors")
        log.exception("planning failed for %s", sid)
        await bus.emit(sid, "system", "error", f"Error: {e}")
        await bus.close(sid)


async def resume_workflow(graph, session_id: str, approved: bool) -> None:
    """Resume from the approval interrupt: booking → notify → execute/reject."""
    sid = session_id
    try:
        await asyncio.wait_for(
            graph.ainvoke(Command(resume={"approved": approved}), config_for(sid)),
            timeout=settings.execution_timeout_s,
        )
    except asyncio.TimeoutError:
        metrics.inc("errors")
        await bus.emit(sid, "system", "error",
                       f"Execution timed out after {settings.execution_timeout_s:.0f}s")
        await bus.close(sid)
    except Exception as e:  # noqa: BLE001
        metrics.inc("errors")
        log.exception("resume failed for %s", sid)
        await bus.emit(sid, "system", "error", f"Error: {e}")
        await bus.close(sid)


async def session_status(graph, session_id: str) -> dict:
    """Derive session phase from checkpoint state — no side tables."""
    snap = await graph.aget_state(config_for(session_id))
    values = dict(snap.values or {})
    if not values:
        return {"session_id": session_id, "phase": "unknown"}

    # Keys can exist with None values (initial state template) — coerce safely
    guard = values.get("guard_verdict") or {}
    approval = values.get("approval") or {}
    booking = values.get("booking_result") or {}
    error = values.get("error")

    if not guard.get("allowed", True):
        phase = "blocked"
    elif error:
        phase = "failed"
    elif "human_approval" in (snap.next or ()):
        phase = "awaiting_approval"
    elif approval.get("approved") is False:
        phase = "rejected"
    elif approval.get("approved"):
        if booking.get("status") == "escalated":
            phase = "escalated"
        elif values.get("execution_result"):
            phase = "completed"
        else:
            phase = "executing"
    else:
        phase = "planning"

    status: dict = {"session_id": session_id, "phase": phase}
    for key in ("guard_verdict", "parsed_intent", "final_plan",
                "booking_result", "execution_result", "approval", "error"):
        if values.get(key) is not None:
            status[key] = values[key]
    return status
