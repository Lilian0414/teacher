from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MemoryCategory(StrEnum):
    PEOPLE = "people"
    PERSONAL = "personal"
    SCHOOL_WORK = "school_work"
    RELATIONSHIPS = "relationships"
    HEALTH_FITNESS = "health_fitness"
    OTHER = "other"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class MemoryAnalysisRequest(BaseModel):
    content: str


class MemoryAnalysis(BaseModel):
    category: MemoryCategory
    person_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    relationship_to_user: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class MemoryExtractionMessage(BaseModel):
    id: str
    role: str
    content: str


class ExistingMemory(BaseModel):
    id: str
    category: MemoryCategory
    content: str
    person_name: str | None = None


class MemoryExtractionRequest(BaseModel):
    conversation_id: str
    messages: list[MemoryExtractionMessage]
    existing_memories: list[ExistingMemory]


class MemoryCandidate(BaseModel):
    category: MemoryCategory
    content: str = Field(min_length=1)
    person_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    relationship_to_user: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_message_ids: list[str] = Field(min_length=1)
    updates_memory_id: str | None = None


class PersonSchema(BaseModel):
    id: str
    canonical_name: str
    aliases: list[str]
    relationship_to_user: str | None


class MemorySchema(BaseModel):
    id: str
    short_id: str
    category: MemoryCategory
    content: str
    person: PersonSchema | None
    source_conversation_id: str | None
    confidence: float | None
    status: MemoryStatus
    created_at: datetime
    updated_at: datetime


class MemoryExtractionResult(BaseModel):
    conversation_id: str
    created: list[MemorySchema] = Field(default_factory=list)
    updated: list[MemorySchema] = Field(default_factory=list)
    skipped_count: int = 0
    error: str | None = None
    retryable: bool = False
