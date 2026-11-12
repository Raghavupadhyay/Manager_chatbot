"""HTTP routes — launch, SSE stream, approve/reject, session, metrics, data."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from ops_copilot.api.schemas import LaunchRequest
from ops_copilot.api.tasks import idempotency, launch_limiter, task_registry
from ops_copilot.config import settings
from ops_copilot.db.database import get_conn
from ops_copilot.observability.metrics import metrics
from ops_copilot.tools.calendar_tool import get_faculty_month_view
from ops_copilot.workflow.events import bus
from ops_copilot.workflow.graph import resume_workflow, run_workflow, session_status

log = logging.getLogger("ops_copilot.api")

router = APIRouter()

def _find_frontend() -> Path:
    override = os.getenv("FRONTEND_DIR")
    if override:
        p = Path(override)
        return p / "index.html" if p.is_dir() else p
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "frontend" / "index.html"
        if candidate.exists():
            return candidate
    return Path.cwd() / "frontend" / "index.html"


_FRONTEND = _find_frontend()


def _graph(request: Request):
    return request.app.state.graph


def _check_api_key(x_api_key: str | None) -> None:
    if settings.auth_api_key and x_api_key != settings.auth_api_key:
        raise HTTPException(401, "Invalid or missing X-API-Key")


# ── UI / health ──────────────────────────────────────────────────────────────

@router.get("/")
def serve_frontend():
    if _FRONTEND.exists():
        return FileResponse(_FRONTEND)
    raise HTTPException(404, "frontend/index.html not found")


@router.get("/health")
def health():
    return {
        "status": "ok",
        "llm_enabled": settings.llm_enabled,
        "model": settings.google_model if settings.llm_enabled else None,
        "tracing": settings.langsmith_tracing,
        "active_tasks": task_registry.active_count,
    }


# ── Workflow control ────────────────────────────────────────────────────────

@router.post("/launch")
async def launch(req: LaunchRequest, request: Request,
                 x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    goal = req.goal.strip()
    if not goal:
        raise HTTPException(400, "Goal cannot be empty")

    client = request.client.host if request.client else "unknown"
    if not launch_limiter.allow(client):
        raise HTTPException(429, "Rate limit exceeded — try again in a minute")

    session_id = str(uuid.uuid4())
    if req.request_id:
        # Process-local cache: a hit means this request already launched a
        # session in this process (checkpoint write may lag by milliseconds,
        # so the phase check would race — cache-hit alone is authoritative).
        cached = idempotency.get(req.request_id)
        if cached:
            return {"session_id": cached, "idempotent_reuse": True}
        idempotency.set(req.request_id, session_id)

    bus.create(session_id)
    task_registry.spawn(session_id, run_workflow(_graph(request), session_id, goal))
    return {"session_id": session_id}


@router.get("/stream/{session_id}")
async def stream(session_id: str):
    q = bus.get(session_id)
    if q is None:
        raise HTTPException(404, "Session not found or stream already closed")

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=settings.sse_heartbeat_s)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"   # SSE comment keeps proxies from closing
                    continue
                if event is None:
                    yield 'data: {"agent": "system", "type": "stream_close", "message": ""}\n\n'
                    bus.drop(session_id)
                    break
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except asyncio.CancelledError:
            # Client disconnected — session state is durable; user may reconnect
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _resume(request: Request, session_id: str, approved: bool):
    status = await session_status(_graph(request), session_id)
    phase = status["phase"]
    if phase == "awaiting_approval":
        task_registry.spawn(session_id, resume_workflow(_graph(request), session_id, approved))
        return {"status": "approved" if approved else "rejected", "session_id": session_id}
    if phase in ("executing", "completed", "escalated", "rejected"):
        return {"status": phase, "session_id": session_id, "idempotent_reuse": True}
    raise HTTPException(409, f"Session is in phase '{phase}' — cannot approve/reject now")


@router.post("/approve/{session_id}")
async def approve(session_id: str, request: Request, x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    return await _resume(request, session_id, True)


@router.post("/reject/{session_id}")
async def reject(session_id: str, request: Request, x_api_key: str | None = Header(default=None)):
    _check_api_key(x_api_key)
    return await _resume(request, session_id, False)


@router.get("/session/{session_id}")
async def get_session(session_id: str, request: Request):
    return await session_status(_graph(request), session_id)


@router.get("/plan/{session_id}")
async def get_plan(session_id: str, request: Request):
    status = await session_status(_graph(request), session_id)
    plan = status.get("final_plan")
    if not plan:
        raise HTTPException(404, "Plan not ready yet")
    return plan


# ── Observability ───────────────────────────────────────────────────────────

@router.get("/metrics")
def get_metrics():
    snapshot = metrics.snapshot()
    snapshot["runtime"] = {
        "active_tasks": task_registry.active_count,
        "active_streams": bus.active_count,
    }
    return snapshot


# ── Domain data (UI panels) ─────────────────────────────────────────────────

@router.get("/faculty")
def list_faculty():
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, name, expertise, subjects, rating, students_taught,
                  time_slot, current_batches, max_batches
           FROM faculty ORDER BY rating DESC"""
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"], "name": r["name"],
            "expertise": json.loads(r["expertise"]),
            "subjects": json.loads(r["subjects"]),
            "rating": r["rating"], "students_taught": r["students_taught"],
            "time_slot": r["time_slot"],
            "available": r["current_batches"] < r["max_batches"],
        }
        for r in rows
    ]


@router.get("/courses")
def list_courses():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, category, subject_area, description, duration_weeks, price "
        "FROM courses ORDER BY category, id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/calendar/{faculty_id}")
def get_calendar(faculty_id: str, year: int | None = None, month: int | None = None):
    import datetime as _dt
    today = _dt.date.today()
    return get_faculty_month_view(faculty_id, year or today.year, month or today.month)
