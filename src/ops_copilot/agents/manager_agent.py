"""Manager agent — goal parsing (Gemini structured output + deterministic
fallback) and plan aggregation with booking candidates."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

log = logging.getLogger("ops_copilot.manager")

_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here"}


def _fallback_parse(goal: str) -> dict:
    """Keyword-based parser — deterministic, no API key needed (CI path)."""
    goal_lower = goal.lower()
    if any(k in goal_lower for k in ("neet", "medical", "mbbs")):
        batch_type, subject_area = "NEET Foundation Batch", "NEET"
    elif any(k in goal_lower for k in ("jee", "iit", "engineering")):
        batch_type, subject_area = "JEE Main Batch", "JEE"
    elif any(k in goal_lower for k in ("banking", "bank", "ibps", "sbi")):
        batch_type, subject_area = "Banking Foundation Batch", "Banking"
    elif any(k in goal_lower for k in ("upsc", "ias", "ips")):
        batch_type, subject_area = "UPSC Prelims Batch", "UPSC"
    elif any(k in goal_lower for k in ("railway", "rrb", "ntpc")):
        batch_type, subject_area = "Railway Foundation Batch", "Railway"
    else:
        batch_type, subject_area = "SSC Foundation Batch", "SSC"

    launch = (datetime.now().replace(day=1) + timedelta(days=44)).replace(day=14)
    return {
        "batch_type": batch_type,
        "subject_area": subject_area,
        "timeline": "next_month",
        "launch_date_estimate": launch.strftime("%B %d, %Y"),
        "expected_duration_weeks": 16,
        "priority": "high",
    }


async def parse_goal(goal: str, on_tokens=None) -> dict:
    """Gemini structured output → validation → fallback parser. Never raises."""
    try:
        from ops_copilot.config import settings
        if settings.llm_enabled:
            from ops_copilot.llm.client import parse_intent
            return await parse_intent(goal, on_tokens=on_tokens)
    except Exception as e:  # noqa: BLE001 — parse must never take the pipeline down
        log.warning("LLM parse failed (%s) — using keyword fallback", e)
    return _fallback_parse(goal)


def build_plan(intent: dict, faculty_result: dict, ops_result: dict,
               marketing_result: dict) -> dict:
    """Aggregate agent outputs into the final execution plan (pure, no I/O)."""
    recommended = faculty_result.get("recommended", [])
    willingness = faculty_result.get("willingness_results", [])
    confirmed = faculty_result.get("confirmed_faculty", [])
    conditional = faculty_result.get("conditional_faculty", [])

    # Rank: confirmed → conditional → rest (by capacity/rating). Dedupe by
    # faculty id — willingness dicts carry extra keys so equality fails.
    taken_ids = {f.get("id") for f in confirmed} | {f.get("id") for f in conditional}
    ranked = confirmed + conditional + [
        r for r in recommended if r.get("id") not in taken_ids
    ]
    primary = ranked[0] if ranked else {"name": "TBD", "available_days": [], "time_slot": "TBD"}
    secondary = ranked[1] if len(ranked) > 1 else None

    base_score = 87
    if not confirmed and conditional:
        base_score = 72
    elif not confirmed and not conditional:
        base_score = 50

    action_items = [
        f"Create '{intent['batch_type']}' batch on LMS by {ops_result.get('lms_setup_start', 'TBD')}",
    ]
    if confirmed:
        action_items.append(f"Finalise contract with {confirmed[0]['name']} (confirmed willing)")
    elif conditional:
        action_items.append(
            f"Follow up with {conditional[0]['name']} to resolve scheduling condition before sign-off")
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

    # Structured willingness (frontend no longer regex-parses strings)
    willingness_structured = [
        {
            "name": f.get("name"),
            "status": f.get("willingness", {}).get("status", "unknown"),
            "message": f.get("willingness", {}).get("message", ""),
        }
        for f in willingness
    ]

    # Ranked booking candidates carried for the auto-fallback ladder (ADR-0009)
    booking_candidates = [
        {
            "faculty_id": f.get("id"),
            "name": f.get("name"),
            "status": f.get("willingness", {}).get("status", "available"),
            "class_days": f.get("available_days", [])[:3],
            "time_slot": f.get("time_slot", ""),
            "rating": f.get("rating"),
        }
        for f in ranked
    ]

    return {
        "batch_name": intent["batch_type"],
        "launch_date": intent["launch_date_estimate"],
        "faculty_primary": primary["name"],
        "faculty_primary_status": primary.get("willingness", {}).get("status", "available").capitalize(),
        "faculty_secondary": secondary["name"] if secondary else "N/A",
        "faculty_willingness": willingness_structured,
        "booking_candidates": booking_candidates,
        "needs_faculty_escalation": not confirmed and not conditional,
        "schedule": ops_result.get("schedule_summary", "TBD"),
        "duration_weeks": intent.get("expected_duration_weeks", 16),
        "expected_students": f"{forecast:,}",
        "expected_revenue": marketing_result.get("expected_revenue", "N/A"),
        "lms_setup_period": ops_result.get("lms_setup_period", "TBD"),
        "marketing_channels": marketing_result.get("top_channels", []),
        "action_items": action_items,
        "total_tasks": len(action_items),
        "readiness_score": base_score,
        "priority": intent.get("priority", "high").upper(),
        "generated_at": datetime.now().isoformat(),
    }
