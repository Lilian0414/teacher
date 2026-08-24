import os
import re
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import get_availability_service, get_conversation_service
from companion.availability import AvailabilityService
from companion.conversation import ConversationRepository, ConversationService
from companion.main import create_app
from companion.memory.schemas import (
    MemoryAnalysisRequest,
    MemoryCategory,
    MemoryExtractionMessage,
    MemoryExtractionRequest,
)
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from companion.providers.groq import GroqLLMProvider
from companion.providers.schemas import (
    ChatMessage,
    ChatRequest,
    LanguageHelpMode,
    LanguageHelpRequest,
)
from companion.settings import get_settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_API_TESTS") != "1" or not get_settings().groq_api_key,
    reason="Groq live tests require RUN_LIVE_API_TESTS=1 and GROQ_API_KEY",
)

CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@pytest.mark.asyncio
async def test_groq_live_chat_and_help() -> None:
    settings = get_settings()
    provider = GroqLLMProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )

    chat = await provider.chat(
        ChatRequest(messages=[ChatMessage(role="user", content="Say hello in one short sentence.")])
    )
    help_response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HELP, content="我想說今天很累")
    )

    assert chat.content
    assert help_response.natural_expression


@pytest.mark.asyncio
async def test_groq_live_help_hint_and_say_contracts() -> None:
    settings = get_settings()
    provider = GroqLLMProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )

    help_response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HELP, content="我今天吃了一顆蘋果")
    )
    hint_response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HINT, content="我今天吃一顆蘋果")
    )
    say_response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.SAY, content="我今天很累")
    )

    assert help_response.natural_expression
    assert not CJK_PATTERN.search(help_response.natural_expression)
    assert help_response.notes_zh and CJK_PATTERN.search(help_response.notes_zh)
    assert 1 <= len(hint_response.hints) <= 3
    assert all(not CJK_PATTERN.search(hint) for hint in hint_response.hints)
    assert say_response.natural_expression
    assert not CJK_PATTERN.search(say_response.natural_expression)


@pytest.mark.asyncio
async def test_groq_live_explicit_memory_analysis_schema() -> None:
    settings = get_settings()
    provider = GroqLLMProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )

    analysis = await provider.analyze_memory(
        MemoryAnalysisRequest(content="Alex is my university classmate.")
    )

    assert analysis.category in MemoryCategory
    assert analysis.confidence is None or 0 <= analysis.confidence <= 1


@pytest.mark.asyncio
async def test_groq_live_memory_extraction_schema() -> None:
    settings = get_settings()
    provider = GroqLLMProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    request = MemoryExtractionRequest(
        conversation_id="live-smoke-conversation",
        messages=[
            MemoryExtractionMessage(
                id="live-message-1",
                role="user",
                content="Alex is my university classmate, and we study together every Thursday.",
            )
        ],
        existing_memories=[],
    )

    candidates = await provider.extract_memory_candidates(request)

    assert candidates
    assert all(
        set(candidate.source_message_ids) == {"live-message-1"} for candidate in candidates
    )


@pytest.mark.asyncio
async def test_groq_live_language_rescue_schema_regression() -> None:
    settings = get_settings()
    provider = GroqLLMProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )

    help_response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HELP, content="我今天吃了一顆蘋果")
    )
    hint_response = await provider.provide_language_help(
        LanguageHelpRequest(mode=LanguageHelpMode.HINT, content="我今天吃一顆蘋果")
    )

    assert help_response.natural_expression
    assert not CJK_PATTERN.search(help_response.natural_expression)
    assert help_response.notes_zh and CJK_PATTERN.search(help_response.notes_zh)
    assert 1 <= len(hint_response.hints) <= 3
    assert hint_response.natural_expression is None


def test_groq_live_help_through_command_endpoint() -> None:
    settings = get_settings()
    assert settings.llm_provider == "groq"

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)

    provider = GroqLLMProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )

    def override_availability() -> Generator[AvailabilityService, None, None]:
        yield AvailabilityService(
            repository=AvailabilityRepository(session),
            clock=lambda: now,
            user_id="default",
        )

    def override_conversation() -> Generator[ConversationService, None, None]:
        yield ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            clock=lambda: now,
            user_id="default",
            context_limit=20,
        )

    app = create_app()
    app.dependency_overrides[get_availability_service] = override_availability
    app.dependency_overrides[get_conversation_service] = override_conversation

    with TestClient(app) as client:
        payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/help 我不會說出軌，Anny 跟 Larry 出軌了"},
        ).json()
        word_payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/help 我不會說蘑菇"},
        ).json()
        hint_payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/hint 我想說我今天累爆了"},
        ).json()
        english_help_payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/help How did you find out about it?"},
        ).json()

    assert payload["ok"] is True
    assert payload["command"] == "help"
    assert payload["natural_expression"]
    assert not CJK_PATTERN.search(payload["natural_expression"])
    assert payload["alternatives"]
    assert all(not CJK_PATTERN.search(item) for item in payload["alternatives"])
    assert CJK_PATTERN.search(payload["notes_zh"])
    assert payload["inserted_into_conversation"] is False
    assert word_payload["natural_expression"].strip(" .").lower() == "mushroom"
    assert {item.strip(" .").lower() for item in word_payload["alternatives"]}.isdisjoint(
        {"fungus", "mush"}
    )
    assert 1 <= len(hint_payload["hints"]) <= 3
    assert all(not CJK_PATTERN.search(item) for item in hint_payload["hints"])
    assert english_help_payload["natural_expression"] is None
    assert english_help_payload["alternatives"] == []
    assert english_help_payload["correction"] is None
    assert CJK_PATTERN.search(english_help_payload["notes_zh"])
