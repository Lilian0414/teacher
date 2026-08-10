from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageSchema(BaseModel):
    id: str
    conversation_id: str
    role: MessageRole
    content: str
    language: str
    source: str
    created_at: datetime


class ConversationSchema(BaseModel):
    id: str
    user_id: str
    mode: str
    private_mode: bool
    started_at: datetime
    ended_at: datetime | None
    messages: list[MessageSchema] = []
