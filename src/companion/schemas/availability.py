from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class AvailabilityState(StrEnum):
    AVAILABLE = "available"
    BUSY = "busy"
    DND = "dnd"


class AvailabilitySnapshot(BaseModel):
    state: AvailabilityState
    source: str
    expires_at: datetime | None
    remaining_seconds: int | None


class LLMStatus(BaseModel):
    provider: str
    model: str | None
    configured: bool
    status: str


class StateResponse(BaseModel):
    status: str
    user_id: str
    availability: AvailabilityState
    override_expires_at: datetime | None
    timezone: str
    remaining_seconds: int | None
    llm: LLMStatus
    due_review_count: int = 0
