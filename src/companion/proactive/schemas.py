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
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class PracticeOutcome(StrEnum):
    LEARNING_SIGNAL_CAPTURED = "learning_signal_captured"
    COMPLETED_NOT_EVALUATED = "completed_not_evaluated"
    ABANDONED = "abandoned"


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
    conversation_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    learning_occurrence_id: str | None = None
    learning_item_id: str | None = None
    outcome: PracticeOutcome | None = None


class ProactiveCheckResponse(BaseModel):
    invitation: InvitationSchema | None = None


class ProactiveRespondRequest(BaseModel):
    decision: InvitationDecision


class ProactiveRespondResponse(BaseModel):
    invitation: InvitationSchema
    review_question: ReviewQuestion | None = None
    review_complete: bool = False
    conversation_starter: str | None = None


class PracticeFinalizeRequest(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
