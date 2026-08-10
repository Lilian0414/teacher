from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class LearningKind(StrEnum):
    EXPRESSION = "expression"
    PHRASE = "phrase"


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


class ReviewAnswerRequest(BaseModel):
    answer: str = Field(min_length=1)


class ReviewResult(BaseModel):
    correct: bool
    accepted_answers: list[str]
    stage: int
    next_review_at: datetime
    next_question: ReviewQuestion | None = None
    complete: bool
