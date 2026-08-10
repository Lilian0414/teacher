from collections.abc import Generator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import (
    get_availability_service,
    get_conversation_service,
    get_llm_provider,
)
from companion.availability import AvailabilityService
from companion.conversation import ConversationRepository, ConversationService
from companion.main import create_app
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from companion.providers.fake import FakeLLMProvider
from companion.providers.schemas import LanguageHelpMode
from tests.support import RecordingLLMProvider


def make_client() -> TestClient:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    provider = FakeLLMProvider()

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
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app)


def make_client_with_provider(provider: RecordingLLMProvider) -> TestClient:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)

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
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app)


def test_help_does_not_insert_into_conversation() -> None:
    with make_client() as client:
        conversation = client.post("/v1/conversations").json()
        payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/help 我不會說出軌", "conversation_id": conversation["id"]},
        ).json()
        stored = client.get(f"/v1/conversations/{conversation['id']}").json()

    assert payload["command"] == "help"
    assert payload["inserted_into_conversation"] is False
    assert payload["natural_expression"]
    assert stored["conversation"]["messages"] == []


def test_hint_has_at_most_three_items_and_no_full_answer() -> None:
    with make_client() as client:
        conversation = client.post("/v1/conversations").json()
        payload = client.post(
            "/v1/commands/execute",
            json={
                "raw": "/hint 我不會說出軌",
                "conversation_id": conversation["id"],
            },
        ).json()
        stored = client.get(f"/v1/conversations/{conversation['id']}").json()

    assert payload["command"] == "hint"
    assert 0 < len(payload["hints"]) <= 3
    assert payload["natural_expression"] is None
    assert stored["conversation"]["messages"] == []


def test_say_inserts_translation_and_assistant_reply() -> None:
    with make_client() as client:
        conversation = client.post("/v1/conversations").json()
        payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/say 今天在學校很辛苦", "conversation_id": conversation["id"]},
        ).json()
        stored = client.get(f"/v1/conversations/{conversation['id']}").json()

    assert payload["command"] == "say"
    assert payload["inserted_into_conversation"] is True
    assert payload["inserted_text"] == "I had a difficult day at school."
    assert payload["assistant_message"]["role"] == "assistant"
    assert [message["role"] for message in stored["conversation"]["messages"]] == [
        "user",
        "assistant",
    ]


def test_missing_command_content_returns_usage() -> None:
    with make_client() as client:
        payload = client.post("/v1/commands/execute", json={"raw": "/help"}).json()

    assert payload["ok"] is False
    assert "Usage" in payload["message"]


def test_say_requires_valid_conversation_id() -> None:
    with make_client() as client:
        missing = client.post("/v1/commands/execute", json={"raw": "/say 你好"}).json()
        invalid = client.post(
            "/v1/commands/execute",
            json={"raw": "/say 你好", "conversation_id": "missing"},
        ).json()

    assert missing["ok"] is False
    assert "conversation_id" in missing["message"]
    assert invalid["ok"] is False
    assert "conversation_id" in invalid["message"]


def test_language_commands_call_provider_and_preserve_full_help_content() -> None:
    provider = RecordingLLMProvider()
    with make_client_with_provider(provider) as client:
        conversation = client.post("/v1/conversations").json()
        help_payload = client.post(
            "/v1/commands/execute",
            json={
                "raw": "/help 我不會說出軌，Anny 跟 Larry 出軌了",
                "conversation_id": conversation["id"],
            },
        ).json()
        english_help_payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/help How did you find out about it?"},
        ).json()
        unnatural_help_payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/help I very tired today."},
        ).json()
        hint_payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/hint 我想說今天很累"},
        ).json()
        say_payload = client.post(
            "/v1/commands/execute",
            json={"raw": "/say 今天很累", "conversation_id": conversation["id"]},
        ).json()

    assert [request.mode for request in provider.language_requests] == [
        LanguageHelpMode.HELP,
        LanguageHelpMode.HELP,
        LanguageHelpMode.HELP,
        LanguageHelpMode.HINT,
        LanguageHelpMode.SAY,
    ]
    assert provider.language_requests[0].content == "我不會說出軌，Anny 跟 Larry 出軌了"
    assert help_payload["natural_expression"] == (
        "Natural English for: 我不會說出軌，Anny 跟 Larry 出軌了"
    )
    assert hint_payload["hints"] == ["cheat on someone", "have an affair", "with Larry"]
    assert english_help_payload["natural_expression"] is None
    assert english_help_payload["correction"] is None
    assert english_help_payload["notes_zh"]
    assert unnatural_help_payload["correction"] == "I am very tired today."
    assert say_payload["inserted_text"] == "Translated: 今天很累"
    assert provider.chat_requests
