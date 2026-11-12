"""Shared pydantic schemas — the LLM output contract (output guard, ADR-0005)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SUBJECT_AREAS = ["SSC", "Banking", "UPSC", "Railway", "NEET", "JEE"]
TIMELINES = ["next_month", "2_weeks", "immediate", "next_quarter"]
PRIORITIES = ["high", "medium", "low"]

_SUBJECT_ALIASES = {
    "ssc": "SSC", "cgl": "SSC", "chsl": "SSC", "mts": "SSC", "staff selection": "SSC",
    "banking": "Banking", "bank": "Banking", "bank po": "Banking", "ibps": "Banking",
    "sbi": "Banking", "rbi": "Banking",
    "upsc": "UPSC", "ias": "UPSC", "ips": "UPSC", "civil services": "UPSC",
    "railway": "Railway", "railways": "Railway", "rrb": "Railway", "ntpc": "Railway",
    "neet": "NEET", "medical": "NEET", "mbbs": "NEET",
    "jee": "JEE", "iit": "JEE", "engineering": "JEE",
}

_TIMELINE_ALIASES = {
    "next_month": "next_month", "next month": "next_month", "in a month": "next_month",
    "2_weeks": "2_weeks", "2 weeks": "2_weeks", "two weeks": "2_weeks", "in 2 weeks": "2_weeks",
    "immediate": "immediate", "immediately": "immediate", "asap": "immediate", "now": "immediate",
    "next_quarter": "next_quarter", "next quarter": "next_quarter",
}

_DATE_FORMAT = "%B %d, %Y"


class IntentSchema(BaseModel):
    """Structured intent extracted from a business goal. Drives everything downstream."""
    batch_type: str = Field(description="Batch/course name, e.g. 'SSC Foundation Batch'")
    subject_area: Literal["SSC", "Banking", "UPSC", "Railway", "NEET", "JEE"]
    timeline: Literal["next_month", "2_weeks", "immediate", "next_quarter"]
    launch_date_estimate: str = Field(description="Launch date, format 'July 14, 2026'")
    expected_duration_weeks: int = Field(ge=4, le=52, default=16)
    priority: Literal["high", "medium", "low"]

    @field_validator("batch_type")
    @classmethod
    def _batch_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("batch_type must not be empty")
        return v

    def to_dict(self) -> dict:
        return self.model_dump()


def _resolve_date(raw: str, timeline: str) -> str:
    """Resolve free-form date text to 'Month DD, YYYY'; fall back to timeline math.

    LLMs have no clock — a hallucinated past date (e.g. 'July 02, 2024' for
    'next month') is rejected and replaced with deterministic timeline math.
    """
    raw = (raw or "").strip()
    try:
        parsed = datetime.strptime(raw, _DATE_FORMAT)
        if parsed >= datetime.now() - timedelta(days=1):
            return parsed.strftime(_DATE_FORMAT)
    except Exception:
        pass
    today = datetime.now()
    if timeline == "2_weeks":
        target = today + timedelta(days=14)
    elif timeline == "next_quarter":
        target = today + timedelta(days=90)
    elif timeline == "immediate":
        target = today + timedelta(days=7)
    else:  # next_month — 14th of next month
        target = (today.replace(day=1) + timedelta(days=44)).replace(day=14)
    return target.strftime(_DATE_FORMAT)


def normalize_intent(raw: dict) -> dict:
    """Canonicalize an LLM-parsed intent before strict validation.

    Handles the loose values observed from live models (e.g. 'SSC Foundation' as
    subject_area, 'next month' as a date, out-of-range durations).
    """
    out = dict(raw or {})
    out.setdefault("batch_type", "New Batch")
    out.setdefault("expected_duration_weeks", 16)
    out.setdefault("priority", "high")

    # subject area — direct match or alias match
    sa = str(out.get("subject_area", "")).strip()
    sa_l = sa.lower()
    if sa not in SUBJECT_AREAS:
        mapped = _SUBJECT_ALIASES.get(sa_l)
        if not mapped:
            for alias, area in _SUBJECT_ALIASES.items():
                if alias in sa_l:
                    mapped = area
                    break
        out["subject_area"] = mapped or "SSC"

    # timeline
    tl = str(out.get("timeline", "next_month")).strip().lower()
    out["timeline"] = _TIMELINE_ALIASES.get(tl, "next_month")

    # priority
    pr = str(out.get("priority", "high")).strip().lower()
    out["priority"] = pr if pr in PRIORITIES else "high"

    # duration — clamp
    try:
        weeks = int(out["expected_duration_weeks"])
    except (TypeError, ValueError):
        weeks = 16
    out["expected_duration_weeks"] = max(4, min(52, weeks))

    # date — resolve/free-form to canonical
    out["launch_date_estimate"] = _resolve_date(str(out.get("launch_date_estimate", "")),
                                                out["timeline"])
    return out
