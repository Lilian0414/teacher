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
        conversation.ended_at = encode_dt(ended_at)
        self._session.commit()
        self._session.refresh(conversation)
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
