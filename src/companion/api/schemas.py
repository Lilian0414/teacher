from pydantic import BaseModel, Field

from companion.learning.schemas import (
    LearningItemSchema,
    ReviewQuestion,
    ReviewResult,
)
from companion.memory.schemas import MemoryExtractionResult, MemorySchema
from companion.schemas.availability import AvailabilitySnapshot
from companion.schemas.conversation import ConversationSchema, MessageSchema


class CommandRequest(BaseModel):
    raw: str
    conversation_id: str | None = None


class CommandResponse(BaseModel):
    command: str
    ok: bool
    message: str
    availability: AvailabilitySnapshot | None = None
    natural_expression: str | None = None
    alternatives: list[str] = Field(default_factory=list)
    notes_zh: str | None = None
    correction: str | None = None
    hints: list[str] = Field(default_factory=list)
    inserted_into_conversation: bool | None = None
    inserted_text: str | None = None
    assistant_message: MessageSchema | None = None
    memory: MemorySchema | None = None
    memories: list[MemorySchema] = Field(default_factory=list)
    confirmation_required: bool = False
    retryable: bool = False
    learning_item: LearningItemSchema | None = None
    review_question: ReviewQuestion | None = None
    review_complete: bool = False


class CreateConversationResponse(BaseModel):
    id: str
    mode: str
    started_at: str


class SendMessageRequest(BaseModel):
    content: str


class SendMessageResponse(BaseModel):
    ok: bool
    user_message: MessageSchema
    assistant_message: MessageSchema | None
    error: str | None = None
    retryable: bool = False


class ConversationResponse(BaseModel):
    conversation: ConversationSchema
    memory_extraction: MemoryExtractionResult | None = None


class MemoryListResponse(BaseModel):
    memories: list[MemorySchema]


class ReviewStateResponse(BaseModel):
    question: ReviewQuestion | None = None
    complete: bool


class ReviewSubmissionResponse(BaseModel):
    result: ReviewResult
