"""
Faculty Tool — queries the SQLite faculty table.
Replaces the old hardcoded FACULTY_DB list.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_conn, init_db


def check_faculty_availability(subject_area: str, launch_date_str: str) -> dict:
    """
    Queries the faculty table for teachers who:
      - have the requested subject_area in their expertise
      - still have capacity (current_batches < max_batches)
    Returns top 2 sorted by rating DESC.
    """
    init_db()  # no-op if DB already exists
    conn = get_conn()

    rows = conn.execute(
        """
        SELECT id, name, expertise, subjects, available_days, time_slot,
               current_batches, max_batches, rating, students_taught
        FROM   faculty
        WHERE  current_batches < max_batches
        ORDER  BY rating DESC
        """
    ).fetchall()
    conn.close()

    # Filter by subject expertise in Python (expertise stored as JSON)
    area_upper = subject_area.upper()
    available = [
        r for r in rows
        if area_upper in [e.upper() for e in json.loads(r["expertise"])]
    ]

    # Fallback: if no subject match, return anyone with capacity
    if not available:
        conn2 = get_conn()
        available = conn2.execute(
            "SELECT * FROM faculty WHERE current_batches < max_batches ORDER BY rating DESC"
        ).fetchall()
        conn2.close()

    # Deserialise JSON fields and convert to plain dicts
    def row_to_dict(r):
        return {
            "id": r["id"],
            "name": r["name"],
            "expertise": json.loads(r["expertise"]),
            "subjects": json.loads(r["subjects"]),
            "available_days": json.loads(r["available_days"]),
            "time_slot": r["time_slot"],
            "current_batches": r["current_batches"],
            "max_batches": r["max_batches"],
            "rating": r["rating"],
            "students_taught": r["students_taught"],
        }

    available_dicts = [row_to_dict(r) for r in available]
    recommended = available_dicts[:2]

    return {
        "available_count": len(available_dicts),
        "recommended": recommended,
        "summary": (
            f"{recommended[0]['name']} available "
            f"({', '.join(recommended[0]['available_days'][:3])})"
            if recommended
            else "No faculty immediately available — escalation needed"
        ),
        "conflict_flag": len(available_dicts) == 0,
    }
