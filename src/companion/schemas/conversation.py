from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MemoryExtractionStatus(StrEnum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


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
    memory_extraction_status: MemoryExtractionStatus
    memory_extraction_attempts: int
    memory_extraction_error: str | None
    memory_extracted_at: datetime | None
    messages: list[MessageSchema] = []
