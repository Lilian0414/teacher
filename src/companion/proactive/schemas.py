from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from companion.learning.schemas import ReviewQuestion


class InvitationKind(StrEnum):
    REVIEW = "review"
    CONVERSATION = "conversation"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    SNOOZED = "snoozed"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class InvitationDecision(StrEnum):
    START = "start"
    SNOOZE = "snooze"
    DISMISS_TODAY = "dismiss_today"


class ProactiveCheckRequest(BaseModel):
    idle_seconds: float = Field(ge=0)
    can_present: bool


class InvitationSchema(BaseModel):
    id: str
    kind: InvitationKind
    status: InvitationStatus
    created_at: datetime
    suppress_until: datetime | None = None
    starter_key: str | None = None
    starter_prompt: str | None = None


class ProactiveCheckResponse(BaseModel):
    invitation: InvitationSchema | None = None


class ProactiveRespondRequest(BaseModel):
    decision: InvitationDecision


class ProactiveRespondResponse(BaseModel):
    invitation: InvitationSchema
    review_question: ReviewQuestion | None = None
    review_complete: bool = False
    conversation_starter: str | None = None
