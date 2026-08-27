from datetime import time
from enum import StrEnum

from pydantic import BaseModel, model_validator


class CorrectionStyle(StrEnum):
    LIGHT = "light"
    NORMAL = "normal"
    INTENSIVE = "intensive"


class ProactiveCadence(StrEnum):
    RARE = "rare"
    NORMAL = "normal"
    FREQUENT = "frequent"


class PracticeBalance(StrEnum):
    REVIEW = "prefer_review"
    BALANCED = "balanced"
    CONVERSATION = "prefer_conversation"


class PreferencesUpdate(BaseModel):
    correction_style: CorrectionStyle | None = None
    proactive_cadence: ProactiveCadence | None = None
    active_hours_start: time | None = None
    active_hours_end: time | None = None
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    practice_balance: PracticeBalance | None = None
    sound_enabled: bool | None = None

    @model_validator(mode="after")
    def paired_windows(self) -> "PreferencesUpdate":
        for name in ("active_hours", "quiet_hours"):
            start = getattr(self, f"{name}_start")
            end = getattr(self, f"{name}_end")
            if (start is None) != (end is None):
                raise ValueError(f"{name}_start and {name}_end must be provided together")
        return self


class LearnerPreferencesSchema(BaseModel):
    correction_style: CorrectionStyle = CorrectionStyle.NORMAL
    proactive_cadence: ProactiveCadence = ProactiveCadence.NORMAL
    active_hours_start: time | None = None
    active_hours_end: time | None = None
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    practice_balance: PracticeBalance = PracticeBalance.BALANCED
    sound_enabled: bool = True
    onboarded: bool = False


class OnboardingOfferSchema(BaseModel):
    should_offer: bool
