"""Manager agent — plan aggregation unit tests (pure function, no I/O)."""
from __future__ import annotations

from ops_copilot.agents.manager_agent import build_plan


def _intent(**over):
    base = {
        "batch_type": "SSC Foundation Batch", "subject_area": "SSC",
        "timeline": "next_month", "launch_date_estimate": "December 14, 2026",
        "expected_duration_weeks": 16, "priority": "high",
    }
    base.update(over)
    return base


def _faculty(fid, name, willingness_status="confirmed"):
    return {
        "id": fid, "name": name, "rating": 4.8,
        "available_days": ["Monday", "Wednesday", "Friday"], "time_slot": "7 PM",
        "willingness": {"status": willingness_status, "message": "ok"},
    }


def _ops():
    return {"schedule_summary": "Mon/Wed/Fri 7pm", "lms_setup_start": "Dec 1",
            "lms_setup_period": "Dec 1 – Dec 3"}


def _marketing():
    return {"forecast_midpoint": 13500, "expected_revenue": "₹3.37 Cr",
            "top_channels": ["YouTube Organic", "Google Ads"]}


class TestBuildPlan:
    def test_ranking_dedupes_by_faculty_id(self):
        f1 = _faculty("F001", "Rakesh Kumar Sir")
        f2 = _faculty("F002", "Priya Sharma Ma'am")
        plan = build_plan(
            intent=_intent(),
            faculty_result={
                "recommended": [f2, f1],           # plain dicts, no willingness
                "willingness_results": [f1, f2],    # willingness-augmented
                "confirmed_faculty": [f1],          # F001 confirmed
                "conditional_faculty": [f2],         # F002 conditional
            },
            ops_result=_ops(), marketing_result=_marketing(),
        )
        names = [c["name"] for c in plan["booking_candidates"]]
        assert len(names) == len(set(names)), f"duplicates in ranking: {names}"
        assert names[0] == "Rakesh Kumar Sir"  # confirmed outranks conditional

    def test_confirmed_primary_and_score(self):
        f1 = _faculty("F001", "Rakesh Kumar Sir")
        plan = build_plan(
            intent=_intent(),
            faculty_result={"recommended": [f1], "willingness_results": [f1],
                            "confirmed_faculty": [f1], "conditional_faculty": []},
            ops_result=_ops(), marketing_result=_marketing(),
        )
        assert plan["faculty_primary"] == "Rakesh Kumar Sir"
        assert plan["faculty_primary_status"] == "Confirmed"
        assert plan["readiness_score"] == 87
        assert plan["needs_faculty_escalation"] is False

    def test_no_willing_faculty_escalates(self):
        f1 = _faculty("F001", "Rakesh Kumar Sir")
        plan = build_plan(
            intent=_intent(),
            faculty_result={"recommended": [f1], "willingness_results": [f1],
                            "confirmed_faculty": [], "conditional_faculty": []},
            ops_result=_ops(), marketing_result=_marketing(),
        )
        assert plan["needs_faculty_escalation"] is True
        assert plan["readiness_score"] == 50
        assert any("Escalate faculty" in a for a in plan["action_items"])

    def test_willingness_is_structured(self):
        f1 = _faculty("F001", "Rakesh Kumar Sir", "conditional")
        plan = build_plan(
            intent=_intent(),
            faculty_result={"recommended": [f1], "willingness_results": [f1],
                            "confirmed_faculty": [], "conditional_faculty": [f1]},
            ops_result=_ops(), marketing_result=_marketing(),
        )
        w = plan["faculty_willingness"][0]
        assert set(w) == {"name", "status", "message"}
        assert w["status"] == "conditional"
        assert plan["readiness_score"] == 72

    def test_action_items_present(self):
        f1 = _faculty("F001", "Rakesh Kumar Sir")
        plan = build_plan(
            intent=_intent(),
            faculty_result={"recommended": [f1], "willingness_results": [f1],
                            "confirmed_faculty": [f1], "conditional_faculty": []},
            ops_result=_ops(), marketing_result=_marketing(),
        )
        assert plan["total_tasks"] == len(plan["action_items"]) >= 8
        assert plan["expected_students"] == "13,500"
