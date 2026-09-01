from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import CursorResult, case, func, select, update
from sqlalchemy.orm import Session

from companion.persistence.models import (
    Conversation,
    LearningOccurrence,
    LearningSignalProcessing,
    Message,
    ProactiveInvitation,
)
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

    def accepted_conversation(self, user_id: str) -> ProactiveInvitation | None:
        return self._session.scalar(
            select(ProactiveInvitation)
            .where(
                ProactiveInvitation.user_id == user_id,
                ProactiveInvitation.kind == InvitationKind.CONVERSATION.value,
                ProactiveInvitation.status == InvitationStatus.ACCEPTED.value,
            )
            .order_by(ProactiveInvitation.responded_at.asc())
        )

    def accepted_conversations(self, user_id: str) -> list[ProactiveInvitation]:
        return list(
            self._session.scalars(
                select(ProactiveInvitation)
                .where(
                    ProactiveInvitation.user_id == user_id,
                    ProactiveInvitation.kind == InvitationKind.CONVERSATION.value,
                    ProactiveInvitation.status == InvitationStatus.ACCEPTED.value,
                )
                .order_by(ProactiveInvitation.responded_at.asc())
            )
        )

    def practices_awaiting_evaluation(self, user_id: str) -> list[ProactiveInvitation]:
        return list(
            self._session.scalars(
                select(ProactiveInvitation).where(
                    ProactiveInvitation.user_id == user_id,
                    ProactiveInvitation.status == InvitationStatus.COMPLETED.value,
                    ProactiveInvitation.outcome == "completed_not_evaluated",
                )
            )
        )

    def processing_state(self, user_message_id: str) -> LearningSignalProcessing | None:
        return self._session.get(LearningSignalProcessing, user_message_id)

    def attach_practice_occurrence(
        self, row: ProactiveInvitation, occurrence: LearningOccurrence
    ) -> None:
        row.outcome = "learning_signal_captured"
        row.learning_occurrence_id = occurrence.id
        row.learning_item_id = occurrence.learning_item_id
        self._session.commit()
        self._session.refresh(row)

    def set_practice_outcome(self, row: ProactiveInvitation, outcome: str) -> None:
        row.outcome = outcome
        self._session.commit()
        self._session.refresh(row)

    def get(self, invitation_id: str, user_id: str) -> ProactiveInvitation | None:
        return self._session.scalar(
            select(ProactiveInvitation).where(
                ProactiveInvitation.id == invitation_id, ProactiveInvitation.user_id == user_id
            )
        )

    def delivery_count(
        self,
        user_id: str,
        local_date: date,
        kind: InvitationKind | None = None,
    ) -> int:
        query = (
            select(func.count())
            .select_from(ProactiveInvitation)
            .where(
                ProactiveInvitation.user_id == user_id,
                ProactiveInvitation.local_date == local_date.isoformat(),
            )
        )
        if kind is not None:
            query = query.where(ProactiveInvitation.kind == kind.value)
        return int(self._session.scalar(query) or 0)

    def latest(self, user_id: str) -> ProactiveInvitation | None:
        return self._session.scalar(
            select(ProactiveInvitation)
            .where(ProactiveInvitation.user_id == user_id)
            .order_by(ProactiveInvitation.created_at.desc())
        )

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

    def resolve(
        self,
        row: ProactiveInvitation,
        *,
        status: InvitationStatus,
        now: datetime,
        suppress_until: datetime | None = None,
        conversation_id: str | None = None,
    ) -> bool:
        if conversation_id is not None:
            conversation = self._session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id, Conversation.user_id == row.user_id
                )
            )
            if conversation is None:
                raise ValueError("conversation_id must belong to the current user")
        result = self._session.execute(
            update(ProactiveInvitation)
            .where(
                ProactiveInvitation.id == row.id,
                ProactiveInvitation.status == InvitationStatus.PENDING.value,
            )
            .values(
                status=status.value,
                responded_at=encode_dt(now),
                suppress_until=encode_dt(suppress_until) if suppress_until else None,
                conversation_id=conversation_id,
            )
        )
        self._session.commit()
        if isinstance(result, CursorResult) and result.rowcount == 1:
            self._session.refresh(row)
            return True
        return False

    def messages_at_or_after(
        self, *, conversation_id: str, boundary: datetime
    ) -> list[Message]:
        return list(
            self._session.scalars(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.created_at >= encode_dt(boundary),
                )
                .order_by(
                    Message.created_at.asc(),
                    case((Message.role == "user", 0), else_=1),
                    Message.id.asc(),
                )
            )
        )

    def conversation_belongs_to(self, conversation_id: str, user_id: str) -> bool:
        return self._session.scalar(
            select(Conversation.id).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        ) is not None

    def validated_practice_evidence(
        self,
        *,
        user_id: str,
        conversation_id: str,
        user_message_id: str,
        assistant_message_id: str,
    ) -> LearningOccurrence | None:
        conversation = self._session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )
        user_message = self._session.scalar(
            select(Message).where(
                Message.id == user_message_id,
                Message.conversation_id == conversation_id,
                Message.role == "user",
            )
        )
        assistant_message = self._session.scalar(
            select(Message).where(
                Message.id == assistant_message_id,
                Message.conversation_id == conversation_id,
                Message.role == "assistant",
            )
        )
        if conversation is None or user_message is None or assistant_message is None:
            raise ValueError(
                "Practice evidence does not belong to the current user and conversation"
            )
        if assistant_message.created_at < user_message.created_at:
            raise ValueError("Assistant message must follow the practice user message")
        return self._session.scalar(
            select(LearningOccurrence).where(
                LearningOccurrence.source_conversation_id == conversation_id,
                LearningOccurrence.source_user_message_id == user_message_id,
                LearningOccurrence.source_assistant_message_id == assistant_message_id,
            )
        )

    def finish_practice(
        self,
        row: ProactiveInvitation,
        *,
        status: InvitationStatus,
        outcome: str,
        now: datetime,
        conversation_id: str | None = None,
        user_message_id: str | None = None,
        assistant_message_id: str | None = None,
        occurrence: LearningOccurrence | None = None,
    ) -> bool:
        result = self._session.execute(
            update(ProactiveInvitation)
            .where(
                ProactiveInvitation.id == row.id,
                ProactiveInvitation.status == InvitationStatus.ACCEPTED.value,
            )
            .values(
                status=status.value,
                outcome=outcome,
                completed_at=encode_dt(now),
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                learning_occurrence_id=occurrence.id if occurrence else None,
                learning_item_id=occurrence.learning_item_id if occurrence else None,
            )
        )
        self._session.commit()
        if isinstance(result, CursorResult) and result.rowcount == 1:
            self._session.refresh(row)
            return True
        return False
