"""Graph nodes — guard, parse, agents, approval interrupt, booking, execution.

Every node returns a partial state update; every node emits SSE events onto
the session bus so the frontend sees live progress.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from langgraph.types import interrupt

from ops_copilot.agents import faculty_agent, manager_agent, marketing_agent, operations_agent
from ops_copilot.config import settings
from ops_copilot.guardrails import input_guard
from ops_copilot.observability.metrics import metrics
from ops_copilot.tools.calendar_tool import try_book
from ops_copilot.tools.notification_tool import send_booking_confirmation, send_escalation
from ops_copilot.workflow.events import bus
from ops_copilot.workflow.state import AgentState

_DATE_FMT = "%B %d, %Y"


def _emit_for(session_id: str):
    async def emit(agent: str, event_type: str, message: str,
                   data: dict | None = None, latency_ms: float | None = None) -> None:
        await bus.emit(session_id, agent, event_type, message, data=data, latency_ms=latency_ms)
    return emit


# ── Guard (ADR-0005) ─────────────────────────────────────────────────────────

async def guard_in_node(state: AgentState) -> dict:
    sid = state["session_id"]
    await bus.emit(sid, "guard", "start", "Screening goal for safety and scope...")
    async with metrics.timer("guard_in"):
        verdict = await input_guard.check(state["goal"])

    if not verdict.allowed:
        metrics.inc("goals_blocked")
        await bus.emit(sid, "guard", "blocked",
                       f"Goal blocked: {verdict.reason}",
                       data={"reason": verdict.reason, "layer": verdict.layer})
        return {"guard_verdict": {
            "allowed": False, "reason": verdict.reason,
            "layer": verdict.layer, "matched_patterns": verdict.matched_patterns,
        }, "error": f"goal blocked: {verdict.reason}"}

    pii_note = (f" · PII scrubbed: {', '.join(verdict.matched_patterns)}"
                if verdict.matched_patterns else "")
    await bus.emit(sid, "guard", "result",
                   f"Goal allowed ({verdict.layer} layer){pii_note}")
    return {"guard_verdict": {
        "allowed": True, "reason": verdict.reason,
        "layer": verdict.layer, "matched_patterns": verdict.matched_patterns,
        "scrubbed_goal": verdict.scrubbed_goal,
    }}


# ── Manager parse (ADR-0003) ─────────────────────────────────────────────────

async def parse_goal_node(state: AgentState) -> dict:
    sid = state["session_id"]
    await bus.emit(sid, "manager", "start",
                   "Analyzing your goal and extracting structured intent...")

    goal = state.get("guard_verdict", {}).get("scrubbed_goal") or state["goal"]

    async def on_tokens(text: str) -> None:
        await bus.emit(sid, "manager", "token", text)

    llm_used = settings.llm_enabled
    async with metrics.timer("parse_goal"):
        intent = await manager_agent.parse_goal(goal, on_tokens=on_tokens if llm_used else None)
    metrics.inc("llm_calls" if llm_used else "fallback_parses")

    await bus.emit(sid, "manager", "result",
                   f"Identified: {intent['batch_type']} · Launch: {intent['launch_date_estimate']}"
                   f" · Priority: {intent['priority'].upper()}")
    return {"parsed_intent": intent}


# ── Domain agents ────────────────────────────────────────────────────────────

async def faculty_node(state: AgentState) -> dict:
    emit = _emit_for(state["session_id"])
    async with metrics.timer("faculty"):
        result = await faculty_agent.run(intent=state["parsed_intent"], emit=emit)
    return {"faculty_result": result}


async def operations_node(state: AgentState) -> dict:
    emit = _emit_for(state["session_id"])
    async with metrics.timer("operations"):
        result = await operations_agent.run(intent=state["parsed_intent"],
                                            faculty_result=state["faculty_result"], emit=emit)
    return {"ops_result": result}


async def marketing_node(state: AgentState) -> dict:
    emit = _emit_for(state["session_id"])
    async with metrics.timer("marketing"):
        result = await marketing_agent.run(intent=state["parsed_intent"], emit=emit)
    return {"marketing_result": result}


async def aggregate_node(state: AgentState) -> dict:
    sid = state["session_id"]
    await bus.emit(sid, "manager", "start", "Compiling results and building execution plan...")
    await asyncio.sleep(0.5)
    async with metrics.timer("aggregate"):
        plan = manager_agent.build_plan(
            intent=state["parsed_intent"],
            faculty_result=state["faculty_result"],
            ops_result=state["ops_result"],
            marketing_result=state["marketing_result"],
        )
    metrics.inc("plans_ready")
    await bus.emit(sid, "manager", "plan_ready",
                   "Execution plan ready — awaiting your approval", data=plan)
    return {"final_plan": plan}


# ── Human-in-the-loop checkpoint (ADR-0001) ─────────────────────────────────

async def human_approval_node(state: AgentState) -> dict:
    """Pause the graph durably until a human approves or rejects the plan."""
    sid = state["session_id"]
    plan = state["final_plan"]
    await bus.emit(sid, "manager", "awaiting_approval",
                   f"Plan checkpoint reached — workflow paused durably (session {sid[:8]})")
    decision = interrupt({
        "session_id": sid,
        "batch_name": plan.get("batch_name"),
        "readiness_score": plan.get("readiness_score"),
        "message": "Approve or reject this execution plan",
    })
    metrics.inc("approvals" if decision.get("approved") else "rejections")
    return {"approval": decision}


# ── Booking ladder (ADR-0009) ────────────────────────────────────────────────

async def reserve_calendar_node(state: AgentState) -> dict:
    sid = state["session_id"]
    plan = state["final_plan"]
    candidates = plan.get("booking_candidates", [])
    batch_name = plan.get("batch_name", "New Batch")
    launch_str = plan.get("launch_date", "")
    weeks = int(plan.get("duration_weeks", 16))

    await bus.emit(sid, "operations", "start",
                   f"Reserving calendar slots for {len(candidates)} candidate(s)...")

    if not candidates:
        result = {"status": "escalated", "reason": "no candidates",
                  "message": "No bookable faculty candidates — escalating"}
        await _emit_escalation(sid, result)
        return {"booking_result": result}

    try:
        launch = datetime.strptime(launch_str, _DATE_FMT)
    except ValueError:
        launch = datetime.now() + timedelta(days=30)

    diffs: list[dict] = []
    async with metrics.timer("reserve_calendar"):
        for shift in range(settings.booking_max_date_shifts + 1):
            shifted = launch + timedelta(weeks=shift)
            shifted_str = shifted.strftime(_DATE_FMT)
            if shift > 0:
                diffs.append({"type": "date_shift",
                              "message": f"Primary window booked out — retrying from "
                                         f"{shifted_str} (+{shift}w)"})
                await bus.emit(sid, "operations", "booking_diff",
                               diffs[-1]["message"], data=diffs[-1])

            for cand in candidates:
                res = try_book(
                    faculty_id=cand["faculty_id"],
                    launch_date_str=shifted_str,
                    duration_weeks=weeks,
                    class_days=cand.get("class_days", []),
                    batch_name=batch_name,
                    session_id=sid,
                )
                if res["ok"]:
                    result = {
                        "status": "booked", "faculty_id": cand["faculty_id"],
                        "faculty_name": cand["name"], "slots_booked": res["slots_booked"],
                        "first_class": res["first_class"], "last_class": res["last_class"],
                        "launch_date": shifted_str, "shifted_weeks": shift,
                        "idempotent": res.get("idempotent_hit", False), "diffs": diffs,
                    }
                    metrics.inc("bookings")
                    await bus.emit(sid, "operations", "result",
                                   f"Booked {cand['name']} — {res['slots_booked']} sessions "
                                   f"({res['first_class']} → {res['last_class']})",
                                   data={"faculty": cand["name"],
                                         "slots": res["slots_booked"]})
                    return {"booking_result": result}

                diffs.append({
                    "type": "candidate_unavailable",
                    "faculty": cand["name"],
                    "reason": res["reason"],
                    "message": f"{cand['name']} unavailable ({res['message']})",
                })
                await bus.emit(sid, "operations", "booking_diff",
                               f"{cand['name']} not bookable — trying next candidate",
                               data=diffs[-1])

    result = {"status": "escalated",
              "reason": "all candidates exhausted",
              "message": f"No bookable slot found after "
                         f"{settings.booking_max_date_shifts + 1} attempts × {len(candidates)} candidates",
              "diffs": diffs}
    await _emit_escalation(sid, result)
    return {"booking_result": result}


async def _emit_escalation(sid: str, result: dict) -> None:
    metrics.inc("escalations")
    await bus.emit(sid, "system", "escalation",
                   f"ESCALATION: {result['message']}", data=result)


# ── Notify ────────────────────────────────────────────────────────────────────

async def notify_node(state: AgentState) -> dict:
    sid = state["session_id"]
    plan = state["final_plan"]
    booking = state.get("booking_result", {})

    if booking.get("status") == "booked":
        receipt = send_booking_confirmation(
            faculty_id=booking["faculty_id"], faculty_name=booking["faculty_name"],
            batch_name=plan.get("batch_name", "Batch"), first_class=booking["first_class"],
            last_class=booking["last_class"], slots_booked=booking["slots_booked"],
        )
        await bus.emit(sid, "faculty", "result",
                       f"Booking confirmation sent to {booking['faculty_name']}")
        return {"notification_result": {"booking_confirmation": receipt}}

    receipt = send_escalation(plan.get("batch_name", "Batch"),
                              booking.get("message", "unknown"))
    await bus.emit(sid, "faculty", "result",
                   "Escalation email sent to operations manager")
    return {"notification_result": {"escalation": receipt}}


# ── Execution ────────────────────────────────────────────────────────────────

async def execute_node(state: AgentState) -> dict:
    sid = state["session_id"]
    plan = state["final_plan"]
    booking = state.get("booking_result", {})

    await bus.emit(sid, "system", "start", "Executing approved plan...")
    for task in plan.get("action_items", []):
        await asyncio.sleep(0.35)
        await bus.emit(sid, "system", "execution", task)

    status = booking.get("status", "no_booking")
    if status == "booked":
        summary = (f"✅ {plan['batch_name']} launched! Faculty {booking['faculty_name']} booked "
                   f"({booking['slots_booked']} sessions). All {plan['total_tasks']} tasks dispatched.")
    else:
        summary = (f"⚠️ {plan['batch_name']} dispatched {plan['total_tasks']} tasks, but "
                   f"faculty booking escalated to the operations manager for manual assignment.")

    await bus.emit(sid, "system", "complete", summary,
                   data={"booking_status": status, "session_id": sid})
    await bus.close(sid)
    return {"execution_result": {"status": status, "summary": summary}}


async def reject_node(state: AgentState) -> dict:
    sid = state["session_id"]
    plan = state["final_plan"]
    await bus.emit(sid, "system", "rejected",
                   f"Plan for {plan.get('batch_name', 'batch')} rejected by approver — "
                   f"no bookings made, workflow ended.",
                   data={"session_id": sid})
    await bus.close(sid)
    return {"execution_result": {"status": "rejected",
                                "summary": "Plan rejected at human checkpoint"}}
