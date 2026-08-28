from companion.learning.schemas import (
    LearningErrorType,
    LearningSignalCandidate,
    LearningSignalConfidence,
    LearningSignalExtraction,
    LearningSignalObservation,
    LearningSignalRequest,
)
from companion.memory.schemas import (
    MemoryAnalysis,
    MemoryAnalysisRequest,
    MemoryCandidate,
    MemoryCategory,
    MemoryExtractionRequest,
)
from companion.providers.errors import LLMProviderError
from companion.providers.schemas import (
    ChatRequest,
    ChatResponse,
    LanguageHelpMode,
    LanguageHelpRequest,
    LanguageHelpResponse,
    SemanticGradeDecision,
    SemanticGradeRequest,
    SemanticGradeVerdict,
    contains_cjk,
)


class RecordingLLMProvider:
    def __init__(self) -> None:
        self.language_requests: list[LanguageHelpRequest] = []
        self.chat_requests: list[ChatRequest] = []
        self.memory_analysis_requests: list[MemoryAnalysisRequest] = []
        self.memory_extraction_requests: list[MemoryExtractionRequest] = []
        self.memory_candidates: list[MemoryCandidate] = []
        self.memory_analysis = MemoryAnalysis(category=MemoryCategory.OTHER, confidence=1.0)
        self.memory_extraction_error: LLMProviderError | None = None
        self.learning_signal: LearningSignalCandidate | None = None
        self.learning_signal_error: Exception | None = None
        self.learning_signal_requests: list[LearningSignalRequest] = []
        self.semantic_grade_requests: list[SemanticGradeRequest] = []
        self.semantic_grade_decision = SemanticGradeDecision(
            verdict=SemanticGradeVerdict.INCORRECT,
            target_preserved=False,
            reason="The answer misses the target.",
        )
        self.semantic_grade_error: LLMProviderError | None = None

    async def grade_review_answer(
        self, request: SemanticGradeRequest
    ) -> SemanticGradeDecision:
        self.semantic_grade_requests.append(request)
        if self.semantic_grade_error is not None:
            raise self.semantic_grade_error
        return self.semantic_grade_decision

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.chat_requests.append(request)
        last_user = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        return ChatResponse(content=f"assistant saw: {last_user}")

    async def provide_language_help(
        self,
        request: LanguageHelpRequest,
    ) -> LanguageHelpResponse:
        self.language_requests.append(request)
        if request.mode == LanguageHelpMode.HELP:
            if not contains_cjk(request.content):
                return LanguageHelpResponse(
                    notes_zh=f"中文意思與語用：{request.content}",
                    correction=(
                        "I am very tired today."
                        if request.content == "I very tired today."
                        else None
                    ),
                )
            return LanguageHelpResponse(
                natural_expression=f"Natural English for: {request.content}",
                alternatives=[f"Alternative for: {request.content}"],
                notes_zh=f"語用差異：{request.content}",
            )
        if request.mode == LanguageHelpMode.HINT:
            return LanguageHelpResponse(
                hints=["cheat on someone", "have an affair", "with Larry"],
                accepted_answers=["Anny cheated on her partner with Larry."],
            )
        if request.mode == LanguageHelpMode.SAY:
            return LanguageHelpResponse(natural_expression=f"Translated: {request.content}")
        raise AssertionError(f"Unsupported mode: {request.mode}")

    async def analyze_memory(self, request: MemoryAnalysisRequest) -> MemoryAnalysis:
        self.memory_analysis_requests.append(request)
        return self.memory_analysis

    async def extract_memory_candidates(
        self,
        request: MemoryExtractionRequest,
    ) -> list[MemoryCandidate]:
        self.memory_extraction_requests.append(request)
        if self.memory_extraction_error is not None:
            raise self.memory_extraction_error
        return list(self.memory_candidates)

    async def extract_learning_signal(
        self, request: LearningSignalRequest
    ) -> LearningSignalExtraction | LearningSignalCandidate | None:
        self.learning_signal_requests.append(request)
        if self.learning_signal_error is not None:
            raise self.learning_signal_error
        return LearningSignalExtraction(
            observation=LearningSignalObservation(
                error_type=LearningErrorType.NONE,
                source_excerpt="",
                correction="",
                confidence=LearningSignalConfidence.LOW,
            ),
            candidate=self.learning_signal,
        )
