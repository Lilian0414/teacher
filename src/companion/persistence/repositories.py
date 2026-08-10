from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from companion.persistence.models import AvailabilityOverride
from companion.schemas.availability import AvailabilityState


def encode_dt(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include timezone")
    return value.isoformat()


def decode_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class AvailabilityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_override(
        self,
        *,
        user_id: str,
        state: AvailabilityState,
        starts_at: datetime,
        expires_at: datetime | None,
        source: str,
    ) -> AvailabilityOverride:
        override = AvailabilityOverride(
            user_id=user_id,
            state=state.value,
            starts_at=encode_dt(starts_at),
            expires_at=encode_dt(expires_at) if expires_at else None,
            source=source,
        )
        self._session.add(override)
        self._session.commit()
        self._session.refresh(override)
        return override

    def latest_active(self, *, user_id: str, now: datetime) -> AvailabilityOverride | None:
        for override in self._session.scalars(self._latest_statement(user_id)):
            expires_at = decode_dt(override.expires_at) if override.expires_at else None
            if expires_at is None or expires_at > now:
                return override
        return None

    def latest(self, *, user_id: str) -> AvailabilityOverride | None:
        return self._session.scalars(self._latest_statement(user_id)).first()

    @staticmethod
    def _latest_statement(user_id: str) -> Select[tuple[AvailabilityOverride]]:
        return (
            select(AvailabilityOverride)
            .where(AvailabilityOverride.user_id == user_id)
            .order_by(AvailabilityOverride.id.desc())
        )
