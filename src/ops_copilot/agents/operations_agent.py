"""Operations agent — LMS capacity + schedule.

Expected students derive from the CRM forecast for the subject area (not a
hardcoded number). Marketing node later re-uses the same CRM data for channels.
"""
from __future__ import annotations

import asyncio

from ops_copilot.tools.crm_tool import get_demand_forecast
from ops_copilot.tools.lms_tool import check_lms_capacity, generate_schedule


async def run(intent: dict, faculty_result: dict, emit) -> dict:
    await emit("operations", "start", "Checking LMS capacity and generating schedule...")
    await asyncio.sleep(0.8)

    forecast = get_demand_forecast(intent.get("subject_area", "SSC"))
    expected_students = forecast.get("forecast_midpoint", 12000)

    recommended = faculty_result.get("recommended", [{}])
    primary_faculty = recommended[0] if recommended else {}

    capacity = check_lms_capacity(expected_students=expected_students)
    schedule = generate_schedule(
        faculty=primary_faculty,
        launch_date_str=intent.get("launch_date_estimate", ""),
        duration_weeks=intent.get("expected_duration_weeks", 16),
    )

    await emit("operations", "result",
               f"LMS status: {capacity['status']} · Schedule: {schedule['schedule_summary']} · "
               f"{schedule['total_sessions']} total sessions")

    return {**capacity, **schedule, "planned_enrollment": expected_students}
