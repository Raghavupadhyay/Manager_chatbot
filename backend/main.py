"""
FastAPI server — entry point.
Endpoints:
  POST /launch          → start a new agent workflow
  GET  /stream/{sid}    → SSE stream of agent events
  POST /approve/{sid}   → trigger simulated execution
  GET  /health          → health check
"""
import asyncio
import contextlib
import json
import os
import sys
import uuid
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

# Add backend/ to sys.path so graph.py, database.py, tools/, agents/ are all importable
sys.path.insert(0, os.path.dirname(__file__))

# Load environment variables from .env if present
load_dotenv()

from graph import run_workflow, simulate_execution, session_queues, session_plans
from database import init_db, get_conn

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

# ── App ──────────────────────────────────────────────────────────────
app = FastAPI(title="Adda247 Managerial Agent - Assessment Task", version="0.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def serve_frontend():
    """Serve the frontend UI out of the box."""
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    raise HTTPException(404, "Frontend index.html not found. Check the project structure.")

# ── Schemas ──────────────────────────────────────────────────────────
class LaunchRequest(BaseModel):
    goal: str


# ── Routes ───────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/launch")
async def launch(req: LaunchRequest):
    if not req.goal.strip():
        raise HTTPException(400, "Goal cannot be empty")

    session_id = str(uuid.uuid4())
    session_queues[session_id] = asyncio.Queue()

    # Kick off workflow as a background task
    asyncio.create_task(run_workflow(session_id, req.goal.strip()))

    return {"session_id": session_id}


@app.get("/stream/{session_id}")
async def stream(session_id: str):
    if session_id not in session_queues:
        raise HTTPException(404, "Session not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        q = session_queues[session_id]
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=120)
            except asyncio.TimeoutError:
                yield "data: {\"type\": \"timeout\"}\n\n"
                break

            if event is None:  # Sentinel — close stream
                yield "data: {\"type\": \"stream_close\"}\n\n"
                break

            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/approve/{session_id}")
async def approve(session_id: str):
    if session_id not in session_plans:
        raise HTTPException(404, "No plan found for this session — workflow may still be running")

    asyncio.create_task(simulate_execution(session_id))
    return {"status": "approved", "message": "Execution started"}


@app.get("/plan/{session_id}")
def get_plan(session_id: str):
    plan = session_plans.get(session_id)
    if not plan:
        raise HTTPException(404, "Plan not ready yet")
    return plan


@app.get("/faculty")
def list_faculty():
    """Return all faculty from the DB (for the UI landing panel)."""
    import json as _json
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, expertise, subjects, rating, students_taught, time_slot, current_batches, max_batches FROM faculty ORDER BY rating DESC"
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "expertise": _json.loads(r["expertise"]),
            "subjects": _json.loads(r["subjects"]),
            "rating": r["rating"],
            "students_taught": r["students_taught"],
            "time_slot": r["time_slot"],
            "available": r["current_batches"] < r["max_batches"],
        }
        for r in rows
    ]


@app.get("/courses")
def list_courses():
    """Return all courses from the DB (for the UI landing panel)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, category, subject_area, description, duration_weeks, price FROM courses ORDER BY category, id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/calendar/{faculty_id}")
def get_calendar(faculty_id: str, year: int = None, month: int = None):
    """Return the month-view calendar for a faculty member."""
    from tools.calendar_tool import get_faculty_month_view
    import datetime
    today = datetime.date.today()
    y = year  or today.year
    m = month or today.month
    return get_faculty_month_view(faculty_id=faculty_id, year=y, month=m)


@app.post("/approve/{session_id}")
async def approve_updated(session_id: str):
    if session_id not in session_plans:
        raise HTTPException(404, "No plan found for this session — workflow may still be running")

    plan = session_plans[session_id]

    # Reserve calendar slots for the primary faculty
    try:
        from tools.calendar_tool import reserve_faculty_slots
        from database import get_conn as _gc
        import json as _json
        conn = _gc()
        row = conn.execute(
            "SELECT id, available_days FROM faculty WHERE name = ?", (plan.get("faculty_primary"),)
        ).fetchone()
        conn.close()
        if row:
            days = _json.loads(row["available_days"])[:3]
            reserve_faculty_slots(
                faculty_id=row["id"],
                launch_date_str=plan.get("launch_date", ""),
                duration_weeks=int(plan.get("duration_weeks", 16)),
                class_days=days,
                batch_name=plan.get("batch_name", "New Batch"),
            )
    except Exception:
        pass   # non-fatal — execution continues regardless

    asyncio.create_task(simulate_execution(session_id))
    return {"status": "approved", "message": "Execution started"}


# ── Entry point (for: uv run python main.py) ──────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
