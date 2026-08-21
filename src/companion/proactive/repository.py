from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from companion.persistence.models import ProactiveInvitation
from companion.persistence.repositories import encode_dt
from companion.proactive.schemas import InvitationKind, InvitationStatus


class ProactiveRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def pending(self, user_id: str) -> ProactiveInvitation | None:
        return self._session.scalar(
            select(ProactiveInvitation)
            .where(ProactiveInvitation.user_id == user_id, ProactiveInvitation.status == "pending")
            .order_by(ProactiveInvitation.created_at.desc())
        )

    def get(self, invitation_id: str, user_id: str) -> ProactiveInvitation | None:
        return self._session.scalar(select(ProactiveInvitation).where(
            ProactiveInvitation.id == invitation_id, ProactiveInvitation.user_id == user_id
        ))

    def delivery_count(
        self,
        user_id: str,
        local_date: date,
        kind: InvitationKind | None = None,
    ) -> int:
        query = select(func.count()).select_from(ProactiveInvitation).where(
            ProactiveInvitation.user_id == user_id,
            ProactiveInvitation.local_date == local_date.isoformat(),
        )
        if kind is not None:
            query = query.where(ProactiveInvitation.kind == kind.value)
        return int(self._session.scalar(query) or 0)

    def latest(self, user_id: str) -> ProactiveInvitation | None:
        return self._session.scalar(select(ProactiveInvitation).where(
            ProactiveInvitation.user_id == user_id
        ).order_by(ProactiveInvitation.created_at.desc()))

    def create(
        self,
        *,
        user_id: str,
        kind: InvitationKind,
        now: datetime,
        local_date: date,
        starter_key: str | None = None,
        starter_prompt: str | None = None,
    ) -> ProactiveInvitation:
        row = ProactiveInvitation(
            id=str(uuid4()),
            user_id=user_id,
            kind=kind.value,
            status=InvitationStatus.PENDING.value,
            created_at=encode_dt(now),
            local_date=local_date.isoformat(),
            starter_key=starter_key,
            starter_prompt=starter_prompt,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def resolve(self, row: ProactiveInvitation, *, status: InvitationStatus, now: datetime,
                suppress_until: datetime | None = None) -> bool:
        result = self._session.execute(update(ProactiveInvitation).where(
            ProactiveInvitation.id == row.id,
            ProactiveInvitation.status == InvitationStatus.PENDING.value,
        ).values(status=status.value, responded_at=encode_dt(now),
                 suppress_until=encode_dt(suppress_until) if suppress_until else None))
        self._session.commit()
        if isinstance(result, CursorResult) and result.rowcount == 1:
            self._session.refresh(row)
            return True
        return False
