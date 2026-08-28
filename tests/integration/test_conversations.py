from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import get_conversation_service, get_llm_provider
from companion.conversation import ConversationRepository, ConversationService
from companion.learning import LearningRepository, LearningService
from companion.main import create_app
from companion.persistence.database import Base, make_engine
from companion.providers.fake import FakeLLMProvider
from companion.schemas.conversation import MessageRole
from tests.support import RecordingLLMProvider


def test_create_conversation_send_message_and_store_both_sides() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    provider = FakeLLMProvider()
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)

    def override_conversation() -> Generator[ConversationService, None, None]:
        yield ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            clock=lambda: now,
            user_id="default",
            context_limit=20,
        )

    app = create_app()
    app.dependency_overrides[get_conversation_service] = override_conversation
    app.dependency_overrides[get_llm_provider] = lambda: provider

    with TestClient(app) as client:
        conversation = client.post("/v1/conversations").json()
        response = client.post(
            f"/v1/conversations/{conversation['id']}/messages",
            json={"content": "I had a difficult day at school."},
        ).json()
        stored = client.get(f"/v1/conversations/{conversation['id']}").json()

    assert response["ok"] is True
    assert response["assistant_message"]["content"].startswith("Fake reply:")
    assert [message["role"] for message in stored["conversation"]["messages"]] == [
        "user",
        "assistant",
    ]


def test_material_chinese_chat_is_redirected_without_conversation_processing() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    provider = RecordingLLMProvider()
    learning_service = LearningService(repository=LearningRepository(session))
    service = ConversationService(
        repository=ConversationRepository(session),
        llm_provider=provider,
        clock=lambda: datetime(2026, 7, 19, 12, tzinfo=UTC),
        learning_service=learning_service,
    )
    app = create_app()
    app.dependency_overrides[get_conversation_service] = lambda: service
    app.dependency_overrides[get_llm_provider] = lambda: provider

    with TestClient(app) as client:
        conversation = client.post("/v1/conversations").json()
        blocked = client.post(
            f"/v1/conversations/{conversation['id']}/messages",
            json={"content": "我今天真的很累。"},
        )
        stored = client.get(f"/v1/conversations/{conversation['id']}").json()

    assert blocked.status_code == 422
    assert blocked.json()["detail"] == (
        "Please try saying that in English. If you need help, use /help or /hint."
    )
    assert stored["conversation"]["messages"] == []
    assert provider.chat_requests == []
    assert provider.learning_signal_requests == []
    assert provider.memory_extraction_requests == []


def test_mixed_english_chat_still_uses_normal_conversation_path() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    provider = RecordingLLMProvider()
    learning_service = LearningService(repository=LearningRepository(session))
    service = ConversationService(
        repository=ConversationRepository(session),
        llm_provider=provider,
        clock=lambda: datetime(2026, 7, 19, 12, tzinfo=UTC),
        learning_service=learning_service,
    )
    app = create_app()
    app.dependency_overrides[get_conversation_service] = lambda: service
    app.dependency_overrides[get_llm_provider] = lambda: provider

    with TestClient(app) as client:
        conversation = client.post("/v1/conversations").json()
        response = client.post(
            f"/v1/conversations/{conversation['id']}/messages",
            json={"content": "I visited 中文 class today."},
        )

    assert response.status_code == 200
    assert response.json()["assistant_message"]["content"] == (
        "assistant saw: I visited 中文 class today."
    )
    assert len(provider.chat_requests) == 1
    assert len(provider.learning_signal_requests) == 1


def test_conversation_history_persists_across_service_instances(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'm1.sqlite3'}"
    engine = make_engine(database_url)
    Base.metadata.create_all(bind=engine)
    provider = FakeLLMProvider()
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)

    with Session(engine) as session:
        repository = ConversationRepository(session)
        first = ConversationService(
            repository=repository,
            llm_provider=provider,
            clock=lambda: now,
            user_id="default",
            context_limit=20,
        )
        conversation = first.create_conversation()
        result = repository.add_message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="Hello.",
            language="en",
            source="terminal",
            created_at=now,
        )
        assert result.content == "Hello."

    with Session(engine) as session:
        restarted = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            clock=lambda: now,
            user_id="default",
            context_limit=20,
        )
        restored = restarted.get_conversation(conversation.id)

    assert len(restored.messages) == 1
    assert restored.messages[0].content == "Hello."
