from typing import Any, Self

import httpx
import pytest

from companion.learning.schemas import LearningSignalRequest
from companion.memory.schemas import (
    ExistingMemory,
    MemoryAnalysisRequest,
    MemoryCategory,
    MemoryExtractionMessage,
    MemoryExtractionRequest,
)
from companion.providers.errors import (
    LLMAuthenticationError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTemporaryError,
    LLMTimeoutError,
)
from companion.providers.fake import FailOnceFakeLLMProvider, FakeLLMProvider
from companion.providers.groq import GroqLLMProvider
from companion.providers.schemas import (
    ChatMessage,
    ChatRequest,
    LanguageHelpMode,
    LanguageHelpRequest,
)


class ScriptedGroqProvider(GroqLLMProvider):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(
            api_key="test-key",
            model="test-model",
            base_url="https://example.invalid",
            timeout_seconds=1,
        )
        self.responses = responses
        self.requests: list[list[dict[str, str]]] = []

    async def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, str] | None,
    ) -> str:
        self.requests.append(messages.copy())
        return self.responses.pop(0)


class StubAsyncClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, *args: object, **kwargs: object) -> httpx.Response:
        return self.response


@pytest.mark.asyncio
async def test_fake_llm_provider_chat_schema() -> None:
    provider = FakeLLMProvider()
    response = await provider.chat(
        ChatRequest(messages=[ChatMessage(role="user", content="I had a hard day.")])
    )

    assert response.content


@pytest.mark.asyncio
async def test_fake_llm_provider_language_help_schema() -> None:
    provider = FakeLLMProvider()
    response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HELP, content="我不會說出軌")
    )

    assert response.natural_expression
    assert len(response.alternatives) <= 2
    assert response.notes_zh


@pytest.mark.asyncio
async def test_fail_once_provider_fails_only_first_chat_without_consuming_help() -> None:
    provider = FailOnceFakeLLMProvider()
    help_response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.SAY, content="今天很累")
    )
    request = ChatRequest(messages=[ChatMessage(role="user", content="I had a difficult day.")])

    assert help_response.natural_expression == "I had a difficult day at school."
    with pytest.raises(LLMTemporaryError, match="Intentional fail-once") as exc_info:
        await provider.chat(request)
    assert exc_info.value.retryable is True
    assert (await provider.chat(request)).content


@pytest.mark.asyncio
async def test_groq_provider_missing_key_error_does_not_include_key() -> None:
    provider = GroqLLMProvider(
        api_key="",
        model="fake-model",
        base_url="https://example.invalid",
        timeout_seconds=1,
    )

    with pytest.raises(Exception) as exc_info:
        await provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hello")]))

    assert "GROQ_API_KEY is not configured" in str(exc_info.value)


def test_provider_error_retryability() -> None:
    assert LLMTimeoutError.retryable is True
    assert LLMTemporaryError.retryable is True
    assert LLMAuthenticationError.retryable is False
    assert LLMRateLimitError.retryable is False
    assert LLMInvalidResponseError.retryable is False


@pytest.mark.asyncio
async def test_groq_memory_analysis_and_extraction_use_structured_schema() -> None:
    provider = ScriptedGroqProvider(
        [
            '{"category":"people","person_name":"Andy","aliases":[],'
            '"relationship_to_user":"classmate","confidence":0.9}',
            '{"candidates":[{"category":"relationships",'
            '"content":"Anny and Larry argued yesterday.","person_name":"Anny",'
            '"aliases":[],"relationship_to_user":null,"confidence":0.95,'
            '"source_message_ids":["message-1"],"updates_memory_id":null}]}',
        ]
    )

    analysis = await provider.analyze_memory(MemoryAnalysisRequest(content="Andy is my classmate"))
    candidates = await provider.extract_memory_candidates(
        MemoryExtractionRequest(
            conversation_id="conversation-1",
            messages=[
                MemoryExtractionMessage(
                    id="message-1",
                    role="user",
                    content="Anny and Larry argued yesterday.",
                )
            ],
            existing_memories=[
                ExistingMemory(
                    id="memory-1",
                    category=MemoryCategory.PEOPLE,
                    content="Andy is my classmate.",
                    person_name="Andy",
                )
            ],
        )
    )

    assert analysis.category == MemoryCategory.PEOPLE
    assert candidates[0].category == MemoryCategory.RELATIONSHIPS
    assert candidates[0].source_message_ids == ["message-1"]


@pytest.mark.asyncio
async def test_groq_invalid_memory_candidate_rejects_entire_response() -> None:
    provider = ScriptedGroqProvider(
        [
            '{"candidates":[{"category":"not-a-category","content":"fact",'
            '"source_message_ids":["message-1"]}]}'
        ]
    )

    with pytest.raises(LLMInvalidResponseError, match="invalid memory candidates"):
        await provider.extract_memory_candidates(
            MemoryExtractionRequest(
                conversation_id="conversation-1",
                messages=[
                    MemoryExtractionMessage(
                        id="message-1",
                        role="user",
                        content="A durable fact.",
                    )
                ],
                existing_memories=[],
            )
        )


@pytest.mark.asyncio
async def test_groq_malformed_learning_signal_fails_safely() -> None:
    provider = ScriptedGroqProvider(['{"candidate":{"stage":99}}'])
    with pytest.raises(LLMInvalidResponseError, match="invalid learning signal"):
        await provider.extract_learning_signal(
            LearningSignalRequest(
                conversation_id="conversation-1",
                user_message_id="user-1",
                assistant_message_id="assistant-1",
                user_content="I very tired.",
                assistant_content="Say: I am very tired.",
            )
        )


@pytest.mark.asyncio
async def test_groq_help_repairs_chinese_in_english_fields_once() -> None:
    provider = ScriptedGroqProvider(
        [
            '{"natural_expression":"Anny 跟 Larry 出軌了",'
            '"alternatives":["Anny 和 Larry 有外遇"],"notes_zh":"描述婚外情。"}',
            '{"natural_expression":"Anny and Larry had an affair.",'
            '"alternatives":["Anny was unfaithful with Larry."],'
            '"notes_zh":"had an affair 較中性；was unfaithful 較委婉。"}',
        ]
    )

    response = await provider.provide_language_help(
        LanguageHelpRequest(
            mode=LanguageHelpMode.HELP,
            content="我不會說出軌，Anny 跟 Larry 出軌了",
        )
    )

    assert response.natural_expression == "Anny and Larry had an affair."
    assert len(provider.requests) == 2
    assert "Critically review" in provider.requests[1][-1]["content"]


@pytest.mark.asyncio
async def test_groq_help_runs_semantic_review_for_structurally_valid_response() -> None:
    provider = ScriptedGroqProvider(
        [
            '{"natural_expression":"mushroom","alternatives":["fungus","mush"],'
            '"notes_zh":"這些都是相關字。"}',
            '{"natural_expression":"mushroom","alternatives":["a mushroom","mushrooms"],'
            '"notes_zh":"前者是單數可數形式，後者是複數形式。"}',
        ]
    )

    response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HELP, content="我不會說蘑菇")
    )

    assert response.alternatives == ["a mushroom", "mushrooms"]
    assert len(provider.requests) == 2
    assert "Critically review" in provider.requests[1][-1]["content"]


@pytest.mark.asyncio
async def test_groq_help_explains_natural_english_without_correction() -> None:
    response_json = (
        '{"natural_expression":null,"alternatives":[],'
        '"notes_zh":"意思是：你是怎麼得知這件事的？","correction":null}'
    )
    provider = ScriptedGroqProvider([response_json, response_json])

    response = await provider.provide_language_help(
        LanguageHelpRequest(
            mode=LanguageHelpMode.HELP,
            content="How did you find out about it?",
        )
    )

    assert response.notes_zh
    assert response.natural_expression is None
    assert response.correction is None
    assert response.alternatives == []


@pytest.mark.asyncio
async def test_groq_help_returns_correction_for_unnatural_english() -> None:
    response_json = (
        '{"natural_expression":null,"alternatives":[],'
        '"notes_zh":"原句缺少 be 動詞。","correction":"I am very tired today."}'
    )
    provider = ScriptedGroqProvider([response_json, response_json])

    response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HELP, content="I very tired today.")
    )

    assert response.correction == "I am very tired today."


@pytest.mark.asyncio
async def test_groq_help_normalizes_primary_translation_from_alternatives() -> None:
    misplaced = (
        '{"natural_expression":null,"alternatives":["I ate an apple today."],'
        '"notes_zh":"表示今天吃了一顆蘋果。","correction":null}'
    )
    provider = ScriptedGroqProvider([misplaced, misplaced])

    response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HELP, content="我今天吃了一顆蘋果")
    )

    assert response.natural_expression == "I ate an apple today."
    assert response.alternatives == []
    assert response.notes_zh == "表示今天吃了一顆蘋果。"


@pytest.mark.asyncio
async def test_groq_hint_ignores_help_fields_and_limits_items() -> None:
    provider = ScriptedGroqProvider(
        [
            '{"alternatives":["I ate an apple today."],'
            '"correction":"I ate an apple today.",'
            '"hints":["ate","an","apple","today"],'
            '"natural_expression":"I ate an apple today.",'
            '"notes_zh":"描述今天吃蘋果。"}'
        ]
    )

    response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HINT, content="我今天吃一顆蘋果")
    )

    assert response.hints == ["ate", "apple", "today"]
    assert response.natural_expression is None
    assert response.alternatives == []


@pytest.mark.asyncio
async def test_groq_hint_repairs_complete_sentence_into_clues() -> None:
    provider = ScriptedGroqProvider(
        [
            '{"hints":["I am exhausted today.","I have had a long day."]}',
        ]
    )

    response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HINT, content="我想說我今天累爆了")
    )

    assert response.hints == ["exhausted", "today", "long"]
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_groq_help_rejects_chinese_in_english_fields_after_repair() -> None:
    invalid = (
        '{"natural_expression":"Anny 跟 Larry 出軌了",'
        '"alternatives":["Anny 和 Larry 有外遇"],"notes_zh":"描述婚外情。"}'
    )
    provider = ScriptedGroqProvider([invalid, invalid])

    with pytest.raises(LLMInvalidResponseError, match="wrong language"):
        await provider.provide_language_help(
            LanguageHelpRequest(mode=LanguageHelpMode.HELP, content="Anny 跟 Larry 出軌了")
        )


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, LLMAuthenticationError),
        (403, LLMAuthenticationError),
        (429, LLMRateLimitError),
        (500, LLMTemporaryError),
        (400, LLMInvalidResponseError),
    ],
)
@pytest.mark.asyncio
async def test_groq_http_errors_are_mapped_to_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    response = httpx.Response(status_code, json={"error": "provider failure"})

    def client_factory(**kwargs: Any) -> StubAsyncClient:
        return StubAsyncClient(response)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    provider = GroqLLMProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.invalid",
        timeout_seconds=1,
    )

    with pytest.raises(expected_error):
        await provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hello")]))


@pytest.mark.asyncio
async def test_groq_non_json_response_is_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = httpx.Response(200, text="not JSON")

    def client_factory(**kwargs: Any) -> StubAsyncClient:
        return StubAsyncClient(response)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    provider = GroqLLMProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.invalid",
        timeout_seconds=1,
    )

    with pytest.raises(LLMInvalidResponseError, match="non-JSON"):
        await provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hello")]))
