"""Calendar tool — conflict checks, month views, and transactional booking (ADR-0009).

Booking guarantees:
  - atomic: all class dates booked + faculty workload bumped in one BEGIN IMMEDIATE
    transaction, or nothing
  - idempotent: bookings are tagged with session_id; re-booking the same session
    returns the existing booking
  - race-safe: conflicts are re-checked inside the write transaction (TOCTOU fix)
  - DB-level: PRIMARY KEY (faculty_id, date) rejects concurrent double-booking

In production this would sit behind Google Calendar / Outlook Graph APIs.
"""
from __future__ import annotations

import sqlite3
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from ops_copilot.db.database import get_conn
from ops_copilot.db.init import init_db

_DAY_MAP = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}


def _parse_launch_date(launch_date_str: str) -> date:
    try:
        return datetime.strptime(launch_date_str, "%B %d, %Y").date()
    except Exception:
        return (datetime.now() + timedelta(days=30)).date()


def class_dates(launch: date, duration_weeks: int, class_days: list[str]) -> list[date]:
    end = launch + timedelta(weeks=duration_weeks)
    weekdays = {_DAY_MAP[d] for d in class_days if d in _DAY_MAP}
    dates = []
    cur = launch
    while cur <= end:
        if cur.weekday() in weekdays:
            dates.append(cur)
        cur += timedelta(days=1)
    return dates


def check_calendar_conflicts(
    faculty_id: str,
    faculty_name: str,
    launch_date_str: str,
    duration_weeks: int,
    class_days: list[str],
) -> dict:
    """Blocked/booked dates that land on class days inside the batch window."""
    init_db()
    launch = _parse_launch_date(launch_date_str)
    end = launch + timedelta(weeks=duration_weeks)
    weekdays = {_DAY_MAP[d] for d in class_days if d in _DAY_MAP}

    conn = get_conn()
    rows = conn.execute(
        """SELECT date, status, notes FROM faculty_calendar
           WHERE faculty_id = ? AND date >= ? AND date <= ?
             AND status IN ('blocked', 'booked') ORDER BY date""",
        (faculty_id, launch.isoformat(), end.isoformat()),
    ).fetchall()
    conn.close()

    conflicts = [
        {"date": r["date"], "status": r["status"], "notes": r["notes"]}
        for r in rows
        if datetime.strptime(r["date"], "%Y-%m-%d").date().weekday() in weekdays
    ]
    is_clear = len(conflicts) == 0
    period = f"{launch.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
    return {
        "faculty_id": faculty_id,
        "faculty_name": faculty_name,
        "period": period,
        "class_days": class_days,
        "is_clear": is_clear,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "summary": (
            f"Calendar clear for {period}" if is_clear
            else f"{len(conflicts)} conflict(s) on class days during {period}"
        ),
    }


def get_faculty_month_view(faculty_id: str, year: int, month: int) -> dict:
    init_db()
    _, days_in_month = monthrange(year, month)
    conn = get_conn()
    rows = conn.execute(
        """SELECT date, status, notes, session_id FROM faculty_calendar
           WHERE faculty_id = ? AND strftime('%Y', date) = ? AND strftime('%m', date) = ?""",
        (faculty_id, str(year), f"{month:02d}"),
    ).fetchall()
    conn.close()

    events = {r["date"]: r for r in rows}
    days = []
    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        ev = events.get(date_str)
        days.append({
            "date": date_str, "day": day,
            "status": ev["status"] if ev else "available",
            "notes": ev["notes"] if ev else None,
            "session_id": ev["session_id"] if ev else None,
        })
    blocked = sum(1 for d in days if d["status"] == "blocked")
    booked = sum(1 for d in days if d["status"] == "booked")
    return {
        "faculty_id": faculty_id, "year": year, "month": month,
        "days_in_month": days_in_month, "days": days,
        "blocked_count": blocked, "booked_count": booked,
        "available_count": days_in_month - blocked - booked,
    }


def try_book(
    faculty_id: str,
    launch_date_str: str,
    duration_weeks: int,
    class_days: list[str],
    batch_name: str,
    session_id: str,
) -> dict:
    """Atomically book all class dates for a faculty — or fail with a reason.

    Returns {ok: bool, reason?: str, detail...}. Idempotent per session.
    """
    init_db()
    launch = _parse_launch_date(launch_date_str)
    dates = class_dates(launch, duration_weeks, class_days)
    iso_dates = [d.isoformat() for d in dates]

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Idempotency — already booked by this session?
        existing = conn.execute(
            "SELECT date FROM faculty_calendar WHERE session_id = ? AND status = 'booked'",
            (session_id,),
        ).fetchall()
        if existing:
            conn.execute("COMMIT")
            return {
                "ok": True, "idempotent_hit": True, "faculty_id": faculty_id,
                "slots_booked": len(existing),
                "first_class": existing[0]["date"], "last_class": existing[-1]["date"],
                "message": f"Booking already exists for session {session_id}",
            }

        # TOCTOU fix — re-check conflicts inside the write transaction
        if iso_dates:
            placeholders = ",".join("?" * len(iso_dates))
            clash = conn.execute(
                f"""SELECT date, status FROM faculty_calendar
                    WHERE faculty_id = ? AND date IN ({placeholders})
                      AND status IN ('blocked', 'booked') LIMIT 1""",
                (faculty_id, *iso_dates),
            ).fetchone()
            if clash:
                conn.execute("ROLLBACK")
                return {
                    "ok": False, "reason": "conflict", "faculty_id": faculty_id,
                    "conflict_date": clash["date"], "conflict_status": clash["status"],
                    "message": f"{faculty_id} has a {clash['status']} slot on {clash['date']}",
                }

        # Capacity — faculty must still have a free batch slot
        frow = conn.execute(
            "SELECT current_batches, max_batches FROM faculty WHERE id = ?", (faculty_id,)
        ).fetchone()
        if not frow:
            conn.execute("ROLLBACK")
            return {"ok": False, "reason": "faculty_not_found", "faculty_id": faculty_id,
                    "message": f"Faculty {faculty_id} not found"}
        if frow["current_batches"] >= frow["max_batches"]:
            conn.execute("ROLLBACK")
            return {"ok": False, "reason": "at_capacity", "faculty_id": faculty_id,
                    "message": f"{faculty_id} is at max batches "
                              f"({frow['current_batches']}/{frow['max_batches']})"}

        # Book — the PK (faculty_id, date) is the final concurrency backstop
        now = datetime.now(timezone.utc).isoformat()
        try:
            for d in iso_dates:
                conn.execute(
                    """INSERT INTO faculty_calendar
                       (faculty_id, date, status, notes, session_id, reserved_at)
                       VALUES (?, ?, 'booked', ?, ?, ?)""",
                    (faculty_id, d, f"Batch: {batch_name}", session_id, now),
                )
            conn.execute(
                "UPDATE faculty SET current_batches = current_batches + 1 WHERE id = ?",
                (faculty_id,),
            )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return {"ok": False, "reason": "conflict", "faculty_id": faculty_id,
                    "message": f"{faculty_id} slot taken concurrently (unique constraint)"}

        return {
            "ok": True, "idempotent_hit": False, "faculty_id": faculty_id,
            "slots_booked": len(iso_dates),
            "first_class": iso_dates[0] if iso_dates else None,
            "last_class": iso_dates[-1] if iso_dates else None,
            "message": f"Booked {len(iso_dates)} class sessions for '{batch_name}'",
        }
    except Exception as e:  # noqa: BLE001 — surface any failure as a failed booking
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        return {"ok": False, "reason": "error", "faculty_id": faculty_id,
                "message": f"Booking failed: {e}"}
    finally:
        conn.close()


def release_booking(session_id: str) -> dict:
    """Release all booked slots owned by a session (reject/supersede path)."""
    init_db()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT DISTINCT faculty_id FROM faculty_calendar
               WHERE session_id = ? AND status = 'booked'""",
            (session_id,),
        ).fetchall()
        conn.execute("DELETE FROM faculty_calendar WHERE session_id = ? AND status = 'booked'",
                     (session_id,))
        for r in rows:
            conn.execute(
                """UPDATE faculty SET current_batches =
                       MAX(0, current_batches - 1) WHERE id = ?""",
                (r["faculty_id"],),
            )
        conn.execute("COMMIT")
        return {"released": len(rows), "faculty_ids": [r["faculty_id"] for r in rows]}
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
