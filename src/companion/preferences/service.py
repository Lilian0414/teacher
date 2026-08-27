from datetime import UTC, datetime, time

from companion.persistence.models import LearnerPreferences
from companion.preferences.repository import PreferencesRepository
from companion.preferences.schemas import (
    CorrectionStyle,
    LearnerPreferencesSchema,
    PracticeBalance,
    PreferencesUpdate,
    ProactiveCadence,
)


class PreferencesService:
    def __init__(self, repository: PreferencesRepository, user_id: str = "default") -> None:
        self._repository = repository
        self._user_id = user_id

    def read(self) -> LearnerPreferencesSchema:
        row = self._repository.get(self._user_id)
        return self._schema(row) if row else LearnerPreferencesSchema()

    def correction_style(self) -> str:
        """Expose the persisted policy to conversation prompt builders."""
        return self.read().correction_style.value

    def has_completed_preferences(self) -> bool:
        """Return whether the learner has established a preference policy."""
        row = self._repository.get(self._user_id)
        return row is not None and row.onboarding_state == "completed"

    def update(self, update: PreferencesUpdate) -> LearnerPreferencesSchema:
        row = self._repository.get(self._user_id)
        now = datetime.now(UTC).isoformat()
        if row is None:
            row = LearnerPreferences(user_id=self._user_id, created_at=now, updated_at=now)
        for field, value in update.model_dump(exclude_unset=True).items():
            # PATCH treats null as "not supplied" so paired windows cannot be
            # accidentally half-cleared. reset() is the supported clearing path.
            if value is not None:
                setattr(row, field, self._encode(value))
        row.onboarding_state = "completed"
        row.updated_at = now
        return self._schema(self._repository.save(row))

    def reset(self) -> LearnerPreferencesSchema:
        row = self._repository.get(self._user_id)
        now = datetime.now(UTC).isoformat()
        if row is None:
            row = LearnerPreferences(user_id=self._user_id, created_at=now, updated_at=now)
        defaults = LearnerPreferencesSchema()
        for field in PreferencesUpdate.model_fields:
            setattr(row, field, self._encode(getattr(defaults, field)))
        row.onboarding_state = "completed"
        row.updated_at = now
        return self._schema(self._repository.save(row))

    def offer_onboarding(self) -> bool:
        """Persist the first-run offer before the UI displays it."""
        row = self._repository.get(self._user_id)
        if row is not None and row.onboarding_state != "pending":
            return False
        now = datetime.now(UTC).isoformat()
        if row is None:
            row = LearnerPreferences(user_id=self._user_id, created_at=now, updated_at=now)
        row.onboarding_state = "offered"
        row.updated_at = now
        self._repository.save(row)
        return True

    def restart_onboarding(self) -> None:
        """Allow an explicit UI command to show onboarding again.

        A completed profile stays completed so reopening the UI cannot silently
        replace the learner-owned policy with the legacy deployment policy.
        """
        row = self._repository.get(self._user_id)
        if row is not None and row.onboarding_state == "completed":
            return
        now = datetime.now(UTC).isoformat()
        if row is None:
            row = LearnerPreferences(user_id=self._user_id, created_at=now, updated_at=now)
        row.onboarding_state = "pending"
        row.updated_at = now
        self._repository.save(row)

    @staticmethod
    def _encode(value: object) -> object:
        if isinstance(value, time):
            return value.strftime("%H:%M")
        return getattr(value, "value", value)

    @staticmethod
    def _schema(row: LearnerPreferences) -> LearnerPreferencesSchema:
        def clock(value: str | None) -> time | None:
            return time.fromisoformat(value) if value else None

        return LearnerPreferencesSchema(
            correction_style=CorrectionStyle(row.correction_style),
            proactive_cadence=ProactiveCadence(row.proactive_cadence),
            active_hours_start=clock(row.active_hours_start),
            active_hours_end=clock(row.active_hours_end),
            quiet_hours_start=clock(row.quiet_hours_start),
            quiet_hours_end=clock(row.quiet_hours_end),
            practice_balance=PracticeBalance(row.practice_balance),
            sound_enabled=row.sound_enabled,
            onboarded=row.onboarding_state != "pending",
        )
