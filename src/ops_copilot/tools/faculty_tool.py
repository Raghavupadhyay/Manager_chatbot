"""Faculty tool — queries the SQLite faculty table."""
from __future__ import annotations

import json

from ops_copilot.db.database import get_conn
from ops_copilot.db.init import init_db

_COLUMNS = ("id, name, expertise, subjects, available_days, time_slot, "
            "current_batches, max_batches, rating, students_taught")


def _row_to_dict(r) -> dict:
    return {
        "id": r["id"], "name": r["name"],
        "expertise": json.loads(r["expertise"]), "subjects": json.loads(r["subjects"]),
        "available_days": json.loads(r["available_days"]),
        "time_slot": r["time_slot"],
        "current_batches": r["current_batches"], "max_batches": r["max_batches"],
        "rating": r["rating"], "students_taught": r["students_taught"],
    }


def check_faculty_availability(subject_area: str, launch_date_str: str) -> dict:
    """Faculty with capacity and matching expertise, ranked by rating."""
    init_db()
    conn = get_conn()
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM faculty WHERE current_batches < max_batches ORDER BY rating DESC"
    ).fetchall()

    area_upper = subject_area.upper()
    available = [
        r for r in rows
        if area_upper in [e.upper() for e in json.loads(r["expertise"])]
    ]
    if not available:  # fallback: any faculty with capacity
        available = rows
    conn.close()

    available_dicts = [_row_to_dict(r) for r in available]
    recommended = available_dicts[:2]
    return {
        "available_count": len(available_dicts),
        "recommended": recommended,
        "summary": (
            f"{recommended[0]['name']} available "
            f"({', '.join(recommended[0]['available_days'][:3])})"
            if recommended else "No faculty immediately available — escalation needed"
        ),
        "conflict_flag": len(available_dicts) == 0,
    }


def get_faculty_by_id(faculty_id: str) -> dict | None:
    init_db()
    conn = get_conn()
    row = conn.execute(f"SELECT {_COLUMNS} FROM faculty WHERE id = ?", (faculty_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None
