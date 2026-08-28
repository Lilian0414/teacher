from typing import Protocol

from companion.learning.schemas import (
    LearningSignalCandidate,
    LearningSignalExtraction,
    LearningSignalRequest,
)
from companion.memory.schemas import (
    MemoryAnalysis,
    MemoryAnalysisRequest,
    MemoryCandidate,
    MemoryExtractionRequest,
)
from companion.providers.schemas import (
    ChatRequest,
    ChatResponse,
    LanguageHelpRequest,
    LanguageHelpResponse,
    SemanticGradeDecision,
    SemanticGradeRequest,
)


class LLMProvider(Protocol):
    async def grade_review_answer(self, request: SemanticGradeRequest) -> SemanticGradeDecision: ...

    async def chat(self, request: ChatRequest) -> ChatResponse: ...

    async def provide_language_help(
        self,
        request: LanguageHelpRequest,
    ) -> LanguageHelpResponse: ...

    async def analyze_memory(self, request: MemoryAnalysisRequest) -> MemoryAnalysis: ...

    async def extract_memory_candidates(
        self,
        request: MemoryExtractionRequest,
    ) -> list[MemoryCandidate]: ...

    async def extract_learning_signal(
        self, request: LearningSignalRequest
    ) -> LearningSignalExtraction | LearningSignalCandidate | None: ...
