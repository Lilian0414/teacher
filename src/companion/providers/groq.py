import json
import re
from typing import Any

import httpx
from pydantic import ValidationError

from companion.learning.prompts import LEARNING_SIGNAL_SYSTEM_PROMPT, learning_signal_user_prompt
from companion.learning.schemas import LearningSignalCandidate, LearningSignalRequest
from companion.memory.prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
    analysis_user_prompt,
    extraction_user_prompt,
)
from companion.memory.schemas import (
    MemoryAnalysis,
    MemoryAnalysisRequest,
    MemoryCandidate,
    MemoryExtractionRequest,
)
from companion.providers.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTemporaryError,
    LLMTimeoutError,
)
from companion.providers.prompts import (
    SEMANTIC_GRADE_SYSTEM_PROMPT,
    conversation_system_prompt,
    language_help_repair_prompt,
    language_help_system_prompt,
    semantic_grade_user_prompt,
)
from companion.providers.schemas import (
    ChatRequest,
    ChatResponse,
    LanguageHelpMode,
    LanguageHelpRequest,
    LanguageHelpResponse,
    SemanticGradeDecision,
    SemanticGradeRequest,
    contains_cjk,
)

FULL_SENTENCE_START = re.compile(
    r"^(?:(?:I(?:['’][A-Za-z]+)?|you|he|she|it|we|they|this|that|there)\b|"
    r"(?:(?:the|a|an|my|your|his|her|our|their)\s+[A-Za-z'-]+|[A-Z][A-Za-z'-]*)"
    r"\s+(?:am|is|are|was|were|have|has|had|do|does|did|can|could|will|would|should|must)\b)",
    re.IGNORECASE,
)
ENGLISH_WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
HINT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "am",
    "at",
    "for",
    "had",
    "has",
    "have",
    "he",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "she",
    "the",
    "they",
    "to",
    "was",
    "we",
    "were",
    "you",
}


class GroqLLMProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self._ensure_configured()
        messages = [
            {
                "role": "system",
                "content": conversation_system_prompt(request.correction_style),
            },
            *[message.model_dump() for message in request.messages],
        ]
        content = await self._complete(messages, response_format=None)
        if not content:
            raise LLMInvalidResponseError("LLM returned an empty chat response")
        return ChatResponse(content=content)

    async def grade_review_answer(self, request: SemanticGradeRequest) -> SemanticGradeDecision:
        """Run one bounded, structured, learning-target-aware grading request."""
        self._ensure_configured()
        content = await self._request_once(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SEMANTIC_GRADE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": semantic_grade_user_prompt(**request.model_dump()),
                    },
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
        )
        try:
            return SemanticGradeDecision.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMInvalidResponseError("LLM returned an invalid semantic grade") from exc

    async def provide_language_help(
        self,
        request: LanguageHelpRequest,
    ) -> LanguageHelpResponse:
        self._ensure_configured()
        messages = [
            {"role": "system", "content": language_help_system_prompt(request.mode)},
            {"role": "user", "content": request.content},
        ]
        for attempt in range(2):
            content = await self._complete(messages, response_format={"type": "json_object"})
            try:
                payload = json.loads(content)
                normalized = self._normalize_language_help_payload(
                    request.mode,
                    request.content,
                    payload,
                )
                response = LanguageHelpResponse.model_validate(normalized)
            except (json.JSONDecodeError, TypeError, ValidationError) as exc:
                if attempt == 1:
                    raise LLMInvalidResponseError(
                        "LLM returned invalid structured response"
                    ) from exc
            else:
                if self._matches_language_help_mode(
                    request.mode,
                    response,
                    source_content=request.content,
                ):
                    if request.mode != LanguageHelpMode.HELP or attempt == 1:
                        return response
                    messages.extend(
                        [
                            {"role": "assistant", "content": content},
                            {
                                "role": "system",
                                "content": language_help_repair_prompt(request.mode),
                            },
                        ]
                    )
                    continue
                if attempt == 1:
                    raise LLMInvalidResponseError(
                        "LLM returned content in the wrong language or schema"
                    )

            messages.extend(
                [
                    {"role": "assistant", "content": content},
                    {"role": "system", "content": language_help_repair_prompt(request.mode)},
                ]
            )

        raise LLMInvalidResponseError("LLM returned invalid structured response")

    async def analyze_memory(self, request: MemoryAnalysisRequest) -> MemoryAnalysis:
        self._ensure_configured()
        content = await self._complete(
            [
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": analysis_user_prompt(request)},
            ],
            response_format={"type": "json_object"},
        )
        try:
            return MemoryAnalysis.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMInvalidResponseError("LLM returned invalid memory analysis") from exc

    async def extract_memory_candidates(
        self,
        request: MemoryExtractionRequest,
    ) -> list[MemoryCandidate]:
        self._ensure_configured()
        content = await self._complete(
            [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": extraction_user_prompt(request)},
            ],
            response_format={"type": "json_object"},
        )
        try:
            payload = json.loads(content)
            raw_candidates = payload["candidates"]
            if not isinstance(raw_candidates, list):
                raise TypeError("candidates must be a list")
            return [MemoryCandidate.model_validate(item) for item in raw_candidates]
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as exc:
            raise LLMInvalidResponseError("LLM returned invalid memory candidates") from exc

    async def extract_learning_signal(
        self, request: LearningSignalRequest
    ) -> LearningSignalCandidate | None:
        self._ensure_configured()
        content = await self._complete(
            [
                {"role": "system", "content": LEARNING_SIGNAL_SYSTEM_PROMPT},
                {"role": "user", "content": learning_signal_user_prompt(request)},
            ],
            response_format={"type": "json_object"},
        )
        try:
            candidate = json.loads(content)["candidate"]
            return None if candidate is None else LearningSignalCandidate.model_validate(candidate)
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as exc:
            raise LLMInvalidResponseError("LLM returned invalid learning signal") from exc

    async def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, str] | None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            return await self._request_once(payload)
        except LLMTemporaryError:
            return await self._request_once(payload)

    def _ensure_configured(self) -> None:
        if not self._api_key:
            raise LLMConfigurationError("GROQ_API_KEY is not configured")

    async def _request_once(self, payload: dict[str, Any]) -> str:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMTemporaryError("LLM request failed temporarily") from exc

        if response.status_code in {401, 403}:
            raise LLMAuthenticationError("LLM authentication failed")
        if response.status_code == 429:
            raise LLMRateLimitError("LLM rate limit reached")
        if response.status_code >= 500:
            raise LLMTemporaryError("LLM service is temporarily unavailable")
        if response.status_code >= 400:
            detail = ""
            try:
                payload = response.json()
                error = payload.get("error", {})
                if isinstance(error, dict):
                    detail = str(error.get("message", ""))
            except ValueError:
                pass
            message = f"Groq rejected model '{self._model}'"
            if detail:
                message = f"{message}: {detail}"
            raise LLMInvalidResponseError(message)

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMInvalidResponseError("LLM returned a non-JSON response") from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMInvalidResponseError("LLM returned an unexpected response") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMInvalidResponseError("LLM returned an empty response")
        return content.strip()

    @staticmethod
    def _matches_language_help_mode(
        mode: LanguageHelpMode,
        response: LanguageHelpResponse,
        *,
        source_content: str,
    ) -> bool:
        def is_english(value: str | None) -> bool:
            return bool(value and value.strip() and not contains_cjk(value))

        def is_chinese(value: str | None) -> bool:
            return bool(value and value.strip() and contains_cjk(value))

        if mode == LanguageHelpMode.HELP:
            if contains_cjk(source_content):
                return bool(
                    is_english(response.natural_expression)
                    and all(is_english(item) for item in response.alternatives)
                    and is_chinese(response.notes_zh)
                    and response.correction is None
                )
            return bool(
                response.natural_expression is None
                and not response.alternatives
                and is_chinese(response.notes_zh)
                and (response.correction is None or is_english(response.correction))
            )
        if mode == LanguageHelpMode.HINT:
            return bool(
                response.hints
                and response.accepted_answers
                and all(
                    is_english(item)
                    and not (FULL_SENTENCE_START.search(item.strip()) and "___" not in item)
                    for item in response.hints
                )
                and all(
                    is_english(item) and "___" not in item for item in response.accepted_answers
                )
            )
        return is_english(response.natural_expression)

    @staticmethod
    def _normalize_language_help_payload(
        mode: LanguageHelpMode,
        source_content: str,
        payload: object,
    ) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise TypeError("Language help payload must be an object")

        def english_string(value: object) -> str | None:
            if not isinstance(value, str):
                return None
            text = value.strip()
            return text if text and not contains_cjk(text) else None

        def string_list(value: object) -> list[str]:
            if not isinstance(value, list):
                return []
            return [text for item in value if (text := english_string(item)) is not None]

        if mode == LanguageHelpMode.HELP:
            notes = payload.get("notes_zh")
            if contains_cjk(source_content):
                natural = english_string(payload.get("natural_expression"))
                alternatives = string_list(payload.get("alternatives"))
                if natural is None:
                    correction = english_string(payload.get("correction"))
                    misplaced = [
                        *alternatives,
                        *([correction] if correction else []),
                    ]
                    if misplaced:
                        natural = misplaced[0]
                        alternatives = misplaced[1:]
                alternatives = [item for item in alternatives if item != natural][:2]
                return {
                    "natural_expression": natural,
                    "alternatives": alternatives,
                    "notes_zh": notes,
                    "correction": None,
                }
            return {
                "natural_expression": None,
                "alternatives": [],
                "notes_zh": notes,
                "correction": english_string(payload.get("correction")),
            }

        if mode == LanguageHelpMode.HINT:
            return {
                "hints": GroqLLMProvider._normalize_hint_items(payload.get("hints")),
                "accepted_answers": [
                    item
                    for item in string_list(payload.get("accepted_answers"))
                    if "___" not in item
                ][:3],
            }

        natural = english_string(payload.get("natural_expression"))
        if natural is None:
            correction = english_string(payload.get("correction"))
            candidates = [
                *string_list(payload.get("alternatives")),
                *([correction] if correction else []),
            ]
            natural = candidates[0] if candidates else None
        return {"natural_expression": natural}

    @staticmethod
    def _normalize_hint_items(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        for raw_item in value:
            if not isinstance(raw_item, str):
                continue
            item = raw_item.strip()
            if not item or contains_cjk(item):
                continue
            is_complete_sentence = "___" not in item and bool(
                FULL_SENTENCE_START.search(item) or item.endswith((".", "!", "?"))
            )
            if is_complete_sentence:
                candidates = [
                    word
                    for word in ENGLISH_WORD.findall(item)
                    if word.casefold() not in HINT_STOPWORDS
                ]
            elif len(ENGLISH_WORD.findall(item)) == 1 and item.casefold() in HINT_STOPWORDS:
                candidates = []
            else:
                candidates = [item]
            for candidate in candidates:
                if candidate not in normalized:
                    normalized.append(candidate)
                if len(normalized) == 3:
                    return normalized
        return normalized
