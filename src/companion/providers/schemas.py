from enum import StrEnum

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    correction_style: str = "normal"


class ChatResponse(BaseModel):
    content: str


class LanguageHelpMode(StrEnum):
    HELP = "help"
    HINT = "hint"
    SAY = "say"


class LanguageHelpRequest(BaseModel):
    mode: LanguageHelpMode
    content: str


class LanguageHelpResponse(BaseModel):
    natural_expression: str | None = None
    alternatives: list[str] = Field(default_factory=list, max_length=2)
    notes_zh: str | None = None
    correction: str | None = None
    hints: list[str] = Field(default_factory=list, max_length=3)
    accepted_answers: list[str] = Field(default_factory=list, max_length=3)


class SemanticGradeVerdict(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNCERTAIN = "uncertain"


class SemanticGradeRequest(BaseModel):
    review_prompt: str = Field(min_length=1, max_length=500)
    kind: str = Field(min_length=1, max_length=50)
    accepted_answers: list[str] = Field(min_length=1, max_length=3)
    submitted_answer: str = Field(min_length=1, max_length=1000)


class SemanticGradeDecision(BaseModel):
    model_config = {"extra": "forbid"}

    verdict: SemanticGradeVerdict
    target_preserved: bool | None = None
    reason: str = Field(min_length=1, max_length=200)


def contains_cjk(value: str) -> bool:
    return any(
        "\u3400" <= character <= "\u4dbf"
        or "\u4e00" <= character <= "\u9fff"
        or "\uf900" <= character <= "\ufaff"
        for character in value
    )
