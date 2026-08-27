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

    def update(self, update: PreferencesUpdate) -> LearnerPreferencesSchema:
        row = self._repository.get(self._user_id)
        now = datetime.now(UTC).isoformat()
        if row is None:
            row = LearnerPreferences(user_id=self._user_id, created_at=now, updated_at=now)
        for field, value in update.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(row, field, self._encode(value))
        row.updated_at = now
        return self._schema(self._repository.save(row))

    def reset(self) -> LearnerPreferencesSchema:
        return self.update(PreferencesUpdate(**LearnerPreferencesSchema().model_dump()))

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
            onboarded=True,
        )
