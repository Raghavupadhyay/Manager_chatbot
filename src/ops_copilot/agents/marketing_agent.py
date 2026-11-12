"""Marketing agent — demand forecast and channel recommendations."""
from __future__ import annotations

import asyncio

from ops_copilot.tools.crm_tool import get_demand_forecast


async def run(intent: dict, emit) -> dict:
    await emit("marketing", "start", "Pulling demand forecast and lead data from CRM...")
    await asyncio.sleep(0.6)
    result = get_demand_forecast(subject_area=intent.get("subject_area", "SSC"))
    await emit("marketing", "result",
               f"Forecast: {result['forecast_range']} · Revenue: {result['expected_revenue']} · "
               f"Top channel: {result['top_channels'][0]}")
    return result
