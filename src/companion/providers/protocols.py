from typing import Protocol

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
)


class LLMProvider(Protocol):
    async def chat(self, request: ChatRequest) -> ChatResponse:
        ...

    async def provide_language_help(
        self,
        request: LanguageHelpRequest,
    ) -> LanguageHelpResponse:
        ...

    async def analyze_memory(self, request: MemoryAnalysisRequest) -> MemoryAnalysis:
        ...

    async def extract_memory_candidates(
        self,
        request: MemoryExtractionRequest,
    ) -> list[MemoryCandidate]:
        ...
