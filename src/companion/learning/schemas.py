from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LearningKind(StrEnum):
    EXPRESSION = "expression"
    PHRASE = "phrase"


class LearningSignalReason(StrEnum):
    CORRECTION = "correction"
    VOCABULARY = "vocabulary"
    USEFUL_EXPRESSION = "useful_expression"


class LearningSignalRequest(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    user_content: str
    assistant_content: str


class LearningSignalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_conversation_id: str
    source_user_message_id: str
    source_assistant_message_id: str
    kind: LearningKind
    review_prompt: str = Field(min_length=1, max_length=500)
    accepted_answers: list[str] = Field(min_length=1, max_length=3)
    reason: LearningSignalReason


class LearningItemSchema(BaseModel):
    id: str
    prompt: str
    kind: LearningKind
    accepted_answers: list[str]
    source_command: str
    stage: int
    next_review_at: datetime
    created_at: datetime
    updated_at: datetime


class ReviewQuestion(BaseModel):
    id: str
    prompt: str
    kind: LearningKind
    position: int = 1
    total: int = 1
    remaining: int = 1


class ReviewAnswerRequest(BaseModel):
    answer: str = Field(min_length=1)
    position: int = Field(default=1, ge=1)
    total: int = Field(default=1, ge=1)


class ReviewResult(BaseModel):
    correct: bool
    prompt: str
    submitted_answer: str
    accepted_answers: list[str]
    stage: int
    next_review_at: datetime
    next_question: ReviewQuestion | None = None
    complete: bool
