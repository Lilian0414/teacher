from sqlalchemy.orm import Session

from companion.persistence.models import LearnerPreferences


class PreferencesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: str) -> LearnerPreferences | None:
        return self._session.get(LearnerPreferences, user_id)

    def save(self, row: LearnerPreferences) -> LearnerPreferences:
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row
