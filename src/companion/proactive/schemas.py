from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from companion.learning.schemas import ReviewQuestion
from companion.schemas.availability import AvailabilityState


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


class ProactiveReason(StrEnum):
    ELIGIBLE = "eligible"
    UI_CANNOT_PRESENT = "ui_cannot_present"
    BUSY = "busy"
    DND = "dnd"
    OUTSIDE_ACTIVE_HOURS = "outside_active_hours"
    QUIET_HOURS = "quiet_hours"
    ACCEPTED_PRACTICE = "accepted_practice"
    PENDING_INVITATION = "pending_invitation"
    SNOOZED = "snoozed"
    DISMISSED_TODAY = "dismissed_today"
    ACCEPTED_COOLDOWN = "accepted_cooldown"
    DAILY_LIMIT = "daily_limit"
    INSUFFICIENT_IDLE = "insufficient_idle"


class ProactiveStatus(BaseModel):
    cadence: str
    uses_legacy_policy: bool
    availability: AvailabilityState
    availability_expires_at: datetime | None = None
    eligible: bool
    reason: ProactiveReason
    due_review_count: int
    next_kind: InvitationKind
    idle_threshold_seconds: int
    idle_remaining_seconds: float
    not_before: datetime | None = None
    daily_delivery_count: int
    daily_delivery_limit: int
    active_hours_start: str | None = None
    active_hours_end: str | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


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
    conversation_id: str | None = None


class ProactiveRespondResponse(BaseModel):
    invitation: InvitationSchema
    review_question: ReviewQuestion | None = None
    review_complete: bool = False
    conversation_starter: str | None = None


class PracticeFinalizeRequest(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
