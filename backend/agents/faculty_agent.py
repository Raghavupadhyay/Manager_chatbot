"""
Faculty Agent — 4-step flow:
  1. DB availability check (capacity)
  2. Calendar conflict check (schedule clash detection)
  3. Email / Slack notification asking for willingness
  4. Collect responses → consolidated report for the Manager
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.faculty_tool import check_faculty_availability
from tools.calendar_tool import check_calendar_conflicts
from tools.notification_tool import send_faculty_notification, get_faculty_response


async def run(intent: dict, emit) -> dict:
    batch_name    = intent.get("batch_type", "New Batch")
    launch_date   = intent.get("launch_date_estimate", "TBD")
    subject_area  = intent.get("subject_area", "SSC")
    duration_weeks = intent.get("expected_duration_weeks", 16)

    # ── Step 1: DB availability (batch capacity) ──────────────────────
    await emit("faculty", "start", "Querying faculty database for availability...")
    await asyncio.sleep(1.0)

    availability = check_faculty_availability(
        subject_area=subject_area,
        launch_date_str=launch_date,
    )
    candidates = availability.get("recommended", [])

    if not candidates:
        await emit("faculty", "result", "No faculty with available capacity — manual assignment needed")
        return {**availability, "calendar_results": [], "willingness_results": [],
                "confirmed_faculty": [], "conditional_faculty": []}

    names = " + ".join(f["name"] for f in candidates)
    await emit("faculty", "result",
               f"Capacity check: {availability['available_count']} available · Shortlisted: {names}")

    # ── Step 2: Calendar conflict check ───────────────────────────────
    await asyncio.sleep(0.4)
    await emit("faculty", "start",
               f"Checking calendar schedules for {len(candidates)} shortlisted faculty...")
    await asyncio.sleep(0.8)

    calendar_clear   = []
    calendar_flagged = []

    for f in candidates:
        class_days = f.get("available_days", ["Monday", "Wednesday", "Friday"])[:3]
        cal = check_calendar_conflicts(
            faculty_id=f["id"],
            faculty_name=f["name"],
            launch_date_str=launch_date,
            duration_weeks=duration_weeks,
            class_days=class_days,
        )

        if cal["is_clear"]:
            await emit("faculty", "result",
                       f"{f['name']} — calendar clear for {cal['period']}")
            calendar_clear.append({**f, "calendar": cal})
        else:
            conflicts_preview = ", ".join(c["date"] for c in cal["conflicts"][:3])
            await emit("faculty", "result",
                       f"{f['name']} — {cal['conflict_count']} conflict(s): {conflicts_preview}"
                       + (" …" if cal["conflict_count"] > 3 else ""))
            calendar_flagged.append({**f, "calendar": cal})

        await asyncio.sleep(0.5)

    # Prefer calendar-clear faculty; fall back to flagged if none clear
    notify_list = calendar_clear if calendar_clear else calendar_flagged
    if calendar_flagged and calendar_clear:
        await emit("faculty", "result",
                   f"{len(calendar_flagged)} faculty flagged with conflicts — will proceed with {len(calendar_clear)} clear")

    # ── Step 3: Send notifications ────────────────────────────────────
    await asyncio.sleep(0.4)
    await emit("faculty", "start",
               f"Sending willingness request via email to {len(notify_list)} faculty...")
    await asyncio.sleep(0.6)

    for f in notify_list:
        send_faculty_notification(
            faculty_id=f["id"],
            faculty_name=f["name"],
            batch_name=batch_name,
            launch_date=launch_date,
            schedule_summary=f.get("time_slot", "TBD"),
            channel="email",
        )
        await emit("faculty", "result", f"Email sent to {f['name']} — awaiting reply...")
        await asyncio.sleep(0.4)

    # ── Step 4: Collect willingness responses ─────────────────────────
    await asyncio.sleep(0.5)
    await emit("faculty", "start", "Collecting faculty responses...")

    willingness_results = []
    for f in notify_list:
        await asyncio.sleep(1.0)
        response = get_faculty_response(faculty_id=f["id"], faculty_name=f["name"])
        status   = response["status"]
        label    = {"confirmed": "CONFIRMED", "conditional": "CONDITIONAL",
                    "unavailable": "UNAVAILABLE"}.get(status, status.upper())
        await emit("faculty", "result",
                   f'{f["name"]} → {label}: "{response["message"]}"')
        willingness_results.append({**f, "willingness": response})

    confirmed   = [w for w in willingness_results if w["willingness"]["status"] == "confirmed"]
    conditional = [w for w in willingness_results if w["willingness"]["status"] == "conditional"]
    unavailable = [w for w in willingness_results if w["willingness"]["status"] == "unavailable"]

    parts = []
    if confirmed:   parts.append(f"{len(confirmed)} confirmed")
    if conditional: parts.append(f"{len(conditional)} conditional")
    if unavailable: parts.append(f"{len(unavailable)} unavailable")

    await emit("faculty", "result",
               f"All checks complete — {' · '.join(parts)} · Forwarding to Manager")

    return {
        **availability,
        "calendar_clear":    calendar_clear,
        "calendar_flagged":  calendar_flagged,
        "willingness_results": willingness_results,
        "confirmed_faculty":   confirmed,
        "conditional_faculty": conditional,
        "unavailable_faculty": unavailable,
    }
