"""Operations Agent — checks LMS capacity and generates a schedule."""
import asyncio
from tools.lms_tool import check_lms_capacity, generate_schedule


async def run(intent: dict, faculty_result: dict, emit) -> dict:
    await emit("operations", "start", "Checking LMS capacity and generating schedule...")
    await asyncio.sleep(1.5)

    recommended = faculty_result.get("recommended", [{}])
    primary_faculty = recommended[0] if recommended else {}

    capacity = check_lms_capacity(expected_students=13000)
    schedule = generate_schedule(
        faculty=primary_faculty,
        launch_date_str=intent.get("launch_date_estimate", ""),
        duration_weeks=intent.get("expected_duration_weeks", 16),
    )

    status = capacity.get("status", "Ready")
    summary = schedule.get("schedule_summary", "TBD")
    await emit("operations", "result",
               f"LMS status: {status} · Schedule: {summary} · {schedule['total_sessions']} total sessions")

    return {**capacity, **schedule}
