"""API request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LaunchRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    request_id: str | None = Field(
        default=None, max_length=64,
        description="Optional idempotency key — repeated launches with the same "
                    "request_id return the original session.",
    )
