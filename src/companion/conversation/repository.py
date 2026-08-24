from datetime import datetime
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from companion.persistence.models import Conversation, Message
from companion.persistence.repositories import encode_dt
from companion.schemas.conversation import MessageRole


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_conversation(self, *, user_id: str, started_at: datetime) -> Conversation:
        conversation = Conversation(
            id=str(uuid4()),
            user_id=user_id,
            mode="text",
            private_mode=False,
            started_at=encode_dt(started_at),
            ended_at=None,
            memory_extraction_status="not_started",
            memory_extraction_attempts=0,
            memory_extraction_error=None,
            memory_extracted_at=None,
        )
        self._session.add(conversation)
        self._session.commit()
        self._session.refresh(conversation)
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self._session.get(Conversation, conversation_id)

    def end_conversation(self, *, conversation_id: str, ended_at: datetime) -> Conversation | None:
        conversation = self.get_conversation(conversation_id)
        if conversation is None:
            return None
        if conversation.ended_at is None:
            conversation.ended_at = encode_dt(ended_at)
            conversation.memory_extraction_status = "pending"
        self._session.commit()
        self._session.refresh(conversation)
        return conversation

    def list_recoverable(self, *, user_id: str) -> list[Conversation]:
        statement: Select[tuple[Conversation]] = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                (Conversation.ended_at.is_(None))
                | (Conversation.memory_extraction_status.in_(("pending", "failed"))),
            )
            .order_by(Conversation.started_at.asc())
        )
        return list(self._session.scalars(statement))

    def start_extraction(self, conversation: Conversation) -> Conversation:
        conversation.memory_extraction_status = "pending"
        conversation.memory_extraction_attempts += 1
        conversation.memory_extraction_error = None
        self._session.commit()
        self._session.refresh(conversation)
        return conversation

    def finish_extraction(
        self,
        conversation: Conversation,
        *,
        completed_at: datetime,
        error: str | None,
        commit: bool = True,
    ) -> Conversation:
        conversation.memory_extraction_status = "failed" if error else "completed"
        conversation.memory_extraction_error = error
        conversation.memory_extracted_at = None if error else encode_dt(completed_at)
        if commit:
            self._session.commit()
            self._session.refresh(conversation)
        else:
            self._session.flush()
        return conversation

    def add_message(
        self,
        *,
        conversation_id: str,
        role: MessageRole,
        content: str,
        language: str,
        source: str,
        created_at: datetime,
    ) -> Message:
        message = Message(
            id=str(uuid4()),
            conversation_id=conversation_id,
            role=role.value,
            content=content,
            language=language,
            source=source,
            created_at=encode_dt(created_at),
        )
        self._session.add(message)
        self._session.commit()
        self._session.refresh(message)
        return message

    def list_messages(self, conversation_id: str) -> list[Message]:
        statement: Select[tuple[Message]] = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(self._session.scalars(statement))

    def recent_messages(self, *, conversation_id: str, limit: int) -> list[Message]:
        statement: Select[tuple[Message]] = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(self._session.scalars(statement))))
