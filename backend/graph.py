"""
LangGraph workflow — orchestrates all agents and manages session state.
Sessions are stored in-memory (suitable for POC).
"""
import asyncio
import sys
import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

# ── Session stores ──────────────────────────────────────────────────
session_queues: dict[str, asyncio.Queue] = {}
session_plans: dict[str, dict] = {}


# ── LangGraph State ─────────────────────────────────────────────────
class AgentState(TypedDict):
    session_id: str
    goal: str
    parsed_intent: Optional[dict]
    faculty_result: Optional[dict]
    ops_result: Optional[dict]
    marketing_result: Optional[dict]
    final_plan: Optional[dict]


# ── Helpers ─────────────────────────────────────────────────────────
async def emit(session_id: str, agent: str, event_type: str, message: str, data: dict = None):
    q = session_queues.get(session_id)
    if q:
        payload = {"agent": agent, "type": event_type, "message": message}
        if data:
            payload["data"] = data
        await q.put(payload)


# ── Graph Nodes ─────────────────────────────────────────────────────
async def parse_goal_node(state: AgentState) -> dict:
    sid = state["session_id"]
    await emit(sid, "manager", "start", "Analyzing your goal and extracting structured intent...")

    sys.path.insert(0, os.path.dirname(__file__))
    from agents.manager_agent import parse_goal
    intent = await parse_goal(state["goal"])

    await emit(sid, "manager", "result",
               f"Identified: {intent['batch_type']} · Launch: {intent['launch_date_estimate']} · Priority: {intent['priority'].upper()}")
    return {"parsed_intent": intent}


async def faculty_node(state: AgentState) -> dict:
    from agents.faculty_agent import run as faculty_run
    sid = state["session_id"]
    result = await faculty_run(
        intent=state["parsed_intent"],
        emit=lambda agent, t, msg: emit(sid, agent, t, msg),
    )
    return {"faculty_result": result}


async def operations_node(state: AgentState) -> dict:
    from agents.operations_agent import run as ops_run
    sid = state["session_id"]
    result = await ops_run(
        intent=state["parsed_intent"],
        faculty_result=state["faculty_result"],
        emit=lambda agent, t, msg: emit(sid, agent, t, msg),
    )
    return {"ops_result": result}


async def marketing_node(state: AgentState) -> dict:
    from agents.marketing_agent import run as mkt_run
    sid = state["session_id"]
    result = await mkt_run(
        intent=state["parsed_intent"],
        emit=lambda agent, t, msg: emit(sid, agent, t, msg),
    )
    return {"marketing_result": result}


async def aggregate_node(state: AgentState) -> dict:
    sid = state["session_id"]
    await emit(sid, "manager", "start", "Compiling results and building execution plan...")
    await asyncio.sleep(0.8)

    from agents.manager_agent import build_plan
    plan = build_plan(
        intent=state["parsed_intent"],
        faculty_result=state["faculty_result"],
        ops_result=state["ops_result"],
        marketing_result=state["marketing_result"],
    )
    session_plans[sid] = plan

    await emit(sid, "manager", "plan_ready",
               "Execution plan ready — awaiting your approval", data=plan)
    return {"final_plan": plan}


# ── Graph Assembly ───────────────────────────────────────────────────
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("parse_goal", parse_goal_node)
    g.add_node("faculty", faculty_node)
    g.add_node("operations", operations_node)
    g.add_node("marketing", marketing_node)
    g.add_node("aggregate", aggregate_node)

    g.add_edge(START, "parse_goal")
    g.add_edge("parse_goal", "faculty")
    g.add_edge("faculty", "operations")
    g.add_edge("operations", "marketing")
    g.add_edge("marketing", "aggregate")
    g.add_edge("aggregate", END)

    return g.compile()


GRAPH = build_graph()


# ── Public API ───────────────────────────────────────────────────────
async def run_workflow(session_id: str, goal: str):
    """Called by main.py as a background task."""
    try:
        await GRAPH.ainvoke({
            "session_id": session_id,
            "goal": goal,
            "parsed_intent": None,
            "faculty_result": None,
            "ops_result": None,
            "marketing_result": None,
            "final_plan": None,
        })
    except Exception as e:
        q = session_queues.get(session_id)
        if q:
            await q.put({"agent": "manager", "type": "error", "message": f"Error: {str(e)}"})
    finally:
        # Signal SSE stream that planning phase is done (stream stays open for execution)
        q = session_queues.get(session_id)
        if q:
            await q.put({"agent": "system", "type": "planning_done", "message": ""})


async def simulate_execution(session_id: str):
    """Simulates task execution after human approval."""
    plan = session_plans.get(session_id)
    if not plan:
        return

    q = session_queues.get(session_id)
    if not q:
        return

    action_items = plan.get("action_items", [])
    for task in action_items:
        await asyncio.sleep(0.6)
        await q.put({"agent": "system", "type": "execution", "message": task})

    await asyncio.sleep(0.5)
    await q.put({"agent": "system", "type": "complete",
                 "message": f"✅ {plan['batch_name']} launch initiated successfully! All {plan['total_tasks']} tasks dispatched."})
    await q.put(None)  # Close SSE stream
