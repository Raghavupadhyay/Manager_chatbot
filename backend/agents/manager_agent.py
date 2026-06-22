"""
Manager Agent — parses the business head's goal using Gemini LLM.
Falls back to keyword-based parsing if no API key is set.
"""
import json
import os
from datetime import datetime, timedelta


def _fallback_parse(goal: str) -> dict:
    """Keyword-based parser — works without any API key."""
    goal_lower = goal.lower()

    if "neet" in goal_lower or "medical" in goal_lower or "mbbs" in goal_lower:
        batch_type, subject_area = "NEET Foundation", "NEET"
    elif "jee" in goal_lower or "iit" in goal_lower or "engineering" in goal_lower:
        batch_type, subject_area = "JEE Main", "JEE"
    elif "banking" in goal_lower or "bank" in goal_lower or "ibps" in goal_lower or "sbi" in goal_lower:
        batch_type, subject_area = "Banking Foundation", "Banking"
    elif "upsc" in goal_lower or "ias" in goal_lower or "ips" in goal_lower:
        batch_type, subject_area = "UPSC Prelims", "UPSC"
    elif "railway" in goal_lower or "rrb" in goal_lower or "ntpc" in goal_lower:
        batch_type, subject_area = "Railway Foundation", "Railway"
    else:
        batch_type, subject_area = "SSC Foundation", "SSC"

    # Estimate launch date ~1 month out, on the 14th
    launch = (datetime.now().replace(day=1) + timedelta(days=44)).replace(day=14)

    return {
        "batch_type": batch_type,
        "subject_area": subject_area,
        "timeline": "next_month",
        "launch_date_estimate": launch.strftime("%B %d, %Y"),
        "expected_duration_weeks": 16,
        "priority": "high",
    }


async def parse_goal(goal: str) -> dict:
    """Use Gemini to parse the goal; fall back gracefully if no key."""
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key or api_key == "your_gemini_api_key_here":
        return _fallback_parse(goal)

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain.schema import HumanMessage

        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=api_key,
            temperature=0,
        )

        prompt = f"""Parse this business goal and return a JSON object.
Goal: "{goal}"

Return JSON with exactly these fields:
- batch_type: string (e.g. "SSC Foundation", "Banking Foundation", "UPSC Prelims")
- subject_area: string (e.g. "SSC", "Banking", "UPSC", "Railway")
- timeline: string ("next_month", "2_weeks", "immediate", "next_quarter")
- launch_date_estimate: string (e.g. "July 14, 2026")
- expected_duration_weeks: number (default 16)
- priority: string ("high", "medium", "low")

Return ONLY valid JSON. No markdown, no explanation."""

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip().strip("```json").strip("```").strip()
        return json.loads(content)

    except Exception:
        return _fallback_parse(goal)


def build_plan(intent: dict, faculty_result: dict, ops_result: dict, marketing_result: dict) -> dict:
    """Aggregate results from all agents into a final execution plan."""
    recommended        = faculty_result.get("recommended", [])
    willingness_results = faculty_result.get("willingness_results", [])
    confirmed          = faculty_result.get("confirmed_faculty", [])
    conditional        = faculty_result.get("conditional_faculty", [])

    # Prefer confirmed faculty for primary assignment
    ranked = confirmed + conditional + [
        r for r in recommended
        if r not in confirmed and r not in conditional
    ]
    primary   = ranked[0] if ranked else {"name": "TBD", "available_days": [], "time_slot": "TBD"}
    secondary = ranked[1] if len(ranked) > 1 else None

    # Willingness note per faculty
    def willingness_note(f: dict) -> str:
        w = f.get("willingness", {})
        status = w.get("status", "unknown")
        msg    = w.get("message", "")
        label  = {"confirmed": "Confirmed", "conditional": "Conditional — needs adjustment", "unavailable": "Unavailable"}.get(status, status)
        return f'{f["name"]} [{label}]: "{msg}"'

    faculty_willingness_notes = [willingness_note(f) for f in willingness_results] if willingness_results else []

    # Readiness score: drops if no confirmed faculty
    base_score = 87
    if not confirmed and conditional:
        base_score = 72   # conditional only — needs follow-up
    elif not confirmed and not conditional:
        base_score = 50   # no willing faculty found

    action_items = [
        f"Create '{intent['batch_type']}' batch on LMS by {ops_result.get('lms_setup_start', 'TBD')}",
    ]

    if confirmed:
        action_items.append(f"Finalise contract with {confirmed[0]['name']} (confirmed willing)")
    elif conditional:
        action_items.append(f"Follow up with {conditional[0]['name']} to resolve scheduling condition before sign-off")
    else:
        action_items.append("Escalate faculty assignment — no willing faculty found")

    if secondary:
        action_items.append(f"Confirm {secondary['name']} as supporting faculty")

    action_items += [
        "Generate course thumbnail and banner (Design Team)",
        "Set up YouTube premiere / announcement video",
        "Launch Google Ads campaign targeting aspirants",
        "Send WhatsApp broadcast to existing leads",
        "Configure test series and study material on LMS",
        "Set batch pricing and payment gateway",
    ]

    forecast = marketing_result.get("forecast_midpoint", 0)
    revenue  = marketing_result.get("expected_revenue", "N/A")

    return {
        "batch_name":             intent["batch_type"],
        "launch_date":            intent["launch_date_estimate"],
        "faculty_primary":        primary["name"],
        "faculty_primary_status": primary.get("willingness", {}).get("status", "available").capitalize(),
        "faculty_secondary":      secondary["name"] if secondary else "N/A",
        "faculty_willingness":    faculty_willingness_notes,
        "schedule":               ops_result.get("schedule_summary", "TBD"),
        "duration_weeks":         intent.get("expected_duration_weeks", 16),
        "expected_students":      f"{forecast:,}",
        "expected_revenue":       revenue,
        "lms_setup_period":       ops_result.get("lms_setup_period", "TBD"),
        "marketing_channels":     marketing_result.get("top_channels", []),
        "action_items":           action_items,
        "total_tasks":            len(action_items),
        "readiness_score":        base_score,
        "priority":               intent.get("priority", "high").upper(),
    }
