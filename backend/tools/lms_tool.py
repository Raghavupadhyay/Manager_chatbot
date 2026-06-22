"""
LMS Tool — queries the SQLite lms_state table.
Replaces the old hardcoded LMS_STATE dict.
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_conn, init_db


def _get_lms_state() -> dict:
    init_db()
    conn = get_conn()
    row = conn.execute("SELECT * FROM lms_state WHERE id = 1").fetchone()
    conn.close()
    return dict(row) if row else {}


def check_lms_capacity(expected_students: int) -> dict:
    state = _get_lms_state()
    total = state["total_capacity"]
    enrolled = state["current_enrollment"]
    active = state["active_batches"]
    max_b = state["max_batches"]

    available_seats = total - enrolled
    can_accommodate = available_seats >= expected_students
    batch_slots_free = max_b - active

    return {
        "can_accommodate": can_accommodate,
        "available_seats": available_seats,
        "batch_slots_free": batch_slots_free,
        "utilization_pct": round(enrolled / total * 100, 1),
        "status": "Ready" if can_accommodate and batch_slots_free > 0 else "Needs Review",
    }


def generate_schedule(faculty: dict, launch_date_str: str, duration_weeks: int) -> dict:
    state = _get_lms_state()
    setup_days = state.get("setup_time_days", 3)

    try:
        launch_date = datetime.strptime(launch_date_str, "%B %d, %Y")
    except Exception:
        launch_date = datetime.now() + timedelta(days=30)

    setup_start = launch_date - timedelta(days=setup_days)
    end_date = launch_date + timedelta(weeks=duration_weeks)

    days = faculty.get("available_days", ["Monday", "Wednesday", "Friday"])[:3]
    time_slot = faculty.get("time_slot", "7:00 PM – 9:00 PM")

    return {
        "launch_date": launch_date.strftime("%B %d, %Y"),
        "end_date": end_date.strftime("%B %d, %Y"),
        "duration_weeks": duration_weeks,
        "lms_setup_start": setup_start.strftime("%B %d, %Y"),
        "lms_setup_period": (
            f"{setup_start.strftime('%b %d')} – "
            f"{(launch_date - timedelta(days=1)).strftime('%b %d, %Y')}"
        ),
        "class_days": days,
        "time_slot": time_slot,
        "sessions_per_week": len(days),
        "total_sessions": len(days) * duration_weeks,
        "schedule_summary": f"{', '.join(days)} | {time_slot}",
    }
