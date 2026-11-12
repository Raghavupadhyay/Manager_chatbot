"""CRM tool — demand forecast from historical data."""
from __future__ import annotations

import json

from ops_copilot.db.database import get_conn
from ops_copilot.db.init import init_db


def get_demand_forecast(subject_area: str) -> dict:
    init_db()
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM crm_data WHERE UPPER(subject_area) = UPPER(?)", (subject_area,)
    ).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM crm_data WHERE subject_area = 'SSC'").fetchone()
    conn.close()

    if not row:
        return {"error": "No CRM data available"}

    data = dict(row)
    top_channels = json.loads(data["top_channels"])
    best_months = json.loads(data["best_launch_months"])
    avg = data["avg_enrollment"]
    lo = int(data["min_enrollment"] * 0.9)
    hi = int(data["max_enrollment"] * 0.85)
    rev = avg * data["avg_revenue_per_student"]

    return {
        "forecast_low": lo,
        "forecast_midpoint": avg,
        "forecast_high": hi,
        "forecast_range": f"{lo:,} – {hi:,} students",
        "current_leads": data["current_leads"],
        "top_channels": top_channels,
        "best_launch_months": best_months,
        "expected_revenue": f"₹{rev / 100000:.1f}L",
        "avg_revenue_per_student": f"₹{data['avg_revenue_per_student']:,}",
        "summary": f"Forecast: ~{avg:,} students | {top_channels[0]} is top channel",
    }
