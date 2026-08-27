from companion.learning.schemas import LearningSignalCandidate, LearningSignalRequest
from companion.memory.schemas import (
    MemoryAnalysis,
    MemoryAnalysisRequest,
    MemoryCandidate,
    MemoryCategory,
    MemoryExtractionRequest,
)
from companion.providers.errors import LLMTemporaryError
from companion.providers.schemas import (
    ChatRequest,
    ChatResponse,
    LanguageHelpMode,
    LanguageHelpRequest,
    LanguageHelpResponse,
    contains_cjk,
)


class FakeLLMProvider:
    def __init__(
        self,
        *,
        memory_candidates: list[MemoryCandidate] | None = None,
        memory_analysis: MemoryAnalysis | None = None,
        learning_signal: LearningSignalCandidate | None = None,
    ) -> None:
        self._memory_candidates = memory_candidates or []
        self._memory_analysis = memory_analysis or MemoryAnalysis(
            category=MemoryCategory.OTHER,
            confidence=1.0,
        )
        self._learning_signal = learning_signal

    async def chat(self, request: ChatRequest) -> ChatResponse:
        last_user = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        return ChatResponse(content=f"Fake reply: {last_user}".strip())

    async def provide_language_help(
        self,
        request: LanguageHelpRequest,
    ) -> LanguageHelpResponse:
        if request.mode == LanguageHelpMode.HELP:
            if not contains_cjk(request.content):
                return LanguageHelpResponse(
                    notes_zh="意思是詢問對方如何得知前面提到的事情。",
                    correction=None,
                )
            return LanguageHelpResponse(
                natural_expression="Anny cheated on her partner with Larry.",
                alternatives=["Anny and Larry had an affair."],
                notes_zh="前句強調對伴侶不忠；後句強調兩人有不正當關係。",
            )
        if request.mode == LanguageHelpMode.HINT:
            return LanguageHelpResponse(
                hints=["exhausted", "worn out", "a long day"],
                accepted_answers=["I was exhausted after a long day."],
            )
        return LanguageHelpResponse(natural_expression="I had a difficult day at school.")

    async def analyze_memory(self, request: MemoryAnalysisRequest) -> MemoryAnalysis:
        return self._memory_analysis

    async def extract_memory_candidates(
        self,
        request: MemoryExtractionRequest,
    ) -> list[MemoryCandidate]:
        return list(self._memory_candidates)

    async def extract_learning_signal(
        self, request: LearningSignalRequest
    ) -> LearningSignalCandidate | None:
        return self._learning_signal


class FailOnceFakeLLMProvider(FakeLLMProvider):
    """UAT provider that fails only its first assistant chat call per process."""

    def __init__(self) -> None:
        super().__init__()
        self._chat_failed = False

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if not self._chat_failed:
            self._chat_failed = True
            raise LLMTemporaryError("Intentional fail-once UAT assistant failure")
        return await super().chat(request)
