"""
Calendar Tool — checks and manages faculty schedule using the faculty_calendar SQLite table.

In production this would integrate with:
  - Google Calendar API (read/write events)
  - Microsoft Outlook / Exchange via Graph API
  - An internal HR scheduling system

Three main operations:
  check_calendar_conflicts()  — are there clashes on class days during the batch window?
  get_faculty_month_view()    — full month calendar for a faculty (for the UI)
  reserve_faculty_slots()     — mark class dates as 'booked' after approval
"""
import sys
import os
from datetime import datetime, timedelta, date
from calendar import monthrange

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_conn, init_db

# Day-name → weekday index (Monday = 0)
_DAY_MAP = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}


def _parse_launch_date(launch_date_str: str) -> date:
    try:
        return datetime.strptime(launch_date_str, "%B %d, %Y").date()
    except Exception:
        return (datetime.now() + timedelta(days=30)).date()


# ── Public API ────────────────────────────────────────────────────────────────

def check_calendar_conflicts(
    faculty_id: str,
    faculty_name: str,
    launch_date_str: str,
    duration_weeks: int,
    class_days: list,
) -> dict:
    """
    Returns any blocked/booked dates that land on class days within the batch window.

    Args:
        faculty_id:       DB faculty ID
        faculty_name:     Human-readable name (for messages)
        launch_date_str:  e.g. "July 14, 2026"
        duration_weeks:   Batch length in weeks
        class_days:       e.g. ["Monday", "Wednesday", "Friday"]

    Returns dict with:
        is_clear       — True if no conflicts
        conflict_count — number of conflicting class days
        conflicts      — list of {date, status, notes}
        summary        — one-line human message
    """
    init_db()

    launch  = _parse_launch_date(launch_date_str)
    end     = launch + timedelta(weeks=duration_weeks)
    weekdays = {_DAY_MAP[d] for d in class_days if d in _DAY_MAP}

    conn = get_conn()
    rows = conn.execute(
        """SELECT date, status, notes FROM faculty_calendar
           WHERE faculty_id = ?
             AND date >= ? AND date <= ?
             AND status IN ('blocked', 'booked')
           ORDER BY date""",
        (faculty_id, launch.isoformat(), end.isoformat()),
    ).fetchall()
    conn.close()

    # Only count dates that actually fall on a class day
    conflicts = [
        {"date": r["date"], "status": r["status"], "notes": r["notes"]}
        for r in rows
        if datetime.strptime(r["date"], "%Y-%m-%d").date().weekday() in weekdays
    ]

    is_clear = len(conflicts) == 0
    period   = f"{launch.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"

    return {
        "faculty_id":     faculty_id,
        "faculty_name":   faculty_name,
        "period":         period,
        "class_days":     class_days,
        "is_clear":       is_clear,
        "conflict_count": len(conflicts),
        "conflicts":      conflicts,
        "summary": (
            f"Calendar clear for {period}"
            if is_clear
            else f"{len(conflicts)} conflict(s) on class days during {period}"
        ),
    }


def get_faculty_month_view(faculty_id: str, year: int, month: int) -> dict:
    """
    Returns a full month view for a faculty member.
    Each day has a status: 'available' | 'blocked' | 'booked'

    Used by the /calendar/{faculty_id} API endpoint and the frontend mini-calendar.
    """
    init_db()

    _, days_in_month = monthrange(year, month)

    conn = get_conn()
    rows = conn.execute(
        """SELECT date, status, notes FROM faculty_calendar
           WHERE faculty_id = ?
             AND strftime('%Y', date) = ?
             AND strftime('%m', date) = ?""",
        (faculty_id, str(year), f"{month:02d}"),
    ).fetchall()
    conn.close()

    # Build lookup: date_str -> event
    events = {r["date"]: {"status": r["status"], "notes": r["notes"]} for r in rows}

    days = []
    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        ev = events.get(date_str)
        days.append({
            "date":   date_str,
            "day":    day,
            "status": ev["status"] if ev else "available",
            "notes":  ev["notes"]  if ev else None,
        })

    blocked = sum(1 for d in days if d["status"] == "blocked")
    booked  = sum(1 for d in days if d["status"] == "booked")

    return {
        "faculty_id":      faculty_id,
        "year":            year,
        "month":           month,
        "days_in_month":   days_in_month,
        "days":            days,
        "blocked_count":   blocked,
        "booked_count":    booked,
        "available_count": days_in_month - blocked - booked,
    }


def reserve_faculty_slots(
    faculty_id: str,
    launch_date_str: str,
    duration_weeks: int,
    class_days: list,
    batch_name: str,
) -> dict:
    """
    Marks all class dates in the batch window as 'booked' for this faculty.
    Called after human approval.

    In production: would create calendar events via Google/Outlook API.
    """
    launch   = _parse_launch_date(launch_date_str)
    end      = launch + timedelta(weeks=duration_weeks)
    weekdays = {_DAY_MAP[d] for d in class_days if d in _DAY_MAP}

    conn     = get_conn()
    reserved = []
    current  = launch

    while current <= end:
        if current.weekday() in weekdays:
            conn.execute(
                """INSERT OR REPLACE INTO faculty_calendar (faculty_id, date, status, notes)
                   VALUES (?, ?, 'booked', ?)""",
                (faculty_id, current.isoformat(), f"Batch: {batch_name}"),
            )
            reserved.append(current.isoformat())
        current += timedelta(days=1)

    conn.commit()
    conn.close()

    return {
        "faculty_id":   faculty_id,
        "batch_name":   batch_name,
        "slots_booked": len(reserved),
        "first_class":  reserved[0]  if reserved else None,
        "last_class":   reserved[-1] if reserved else None,
        "message":      f"Booked {len(reserved)} class sessions for '{batch_name}'",
    }
