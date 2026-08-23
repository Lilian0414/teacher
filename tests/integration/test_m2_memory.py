from collections.abc import Generator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import (
    get_availability_service,
    get_conversation_service,
    get_llm_provider,
    get_memory_service,
)
from companion.availability import AvailabilityService
from companion.conversation import ConversationRepository, ConversationService
from companion.main import create_app
from companion.memory import MemoryContextBuilder, MemoryRepository, MemoryService
from companion.memory.schemas import MemoryAnalysis, MemoryCandidate, MemoryCategory
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from companion.providers.errors import LLMTemporaryError
from tests.support import RecordingLLMProvider


def make_m2_client() -> tuple[TestClient, RecordingLLMProvider, MemoryRepository]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    provider = RecordingLLMProvider()
    memory_repository = MemoryRepository(session)
    conversation_repository = ConversationRepository(session)
    memory_service = MemoryService(
        repository=memory_repository,
        conversation_repository=conversation_repository,
        llm_provider=provider,
        clock=lambda: now,
    )
    conversation_service = ConversationService(
        repository=conversation_repository,
        llm_provider=provider,
        clock=lambda: now,
        user_id="default",
        context_limit=20,
        memory_context_builder=MemoryContextBuilder(memory_repository, limit=5),
    )

    def override_availability() -> Generator[AvailabilityService, None, None]:
        yield AvailabilityService(
            repository=AvailabilityRepository(session),
            clock=lambda: now,
            user_id="default",
        )

    def override_conversation() -> Generator[ConversationService, None, None]:
        yield conversation_service

    def override_memory() -> Generator[MemoryService, None, None]:
        yield memory_service

    app = create_app()
    app.dependency_overrides[get_availability_service] = override_availability
    app.dependency_overrides[get_conversation_service] = override_conversation
    app.dependency_overrides[get_memory_service] = override_memory
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app), provider, memory_repository


def test_memory_commands_remember_search_and_confirmed_forget() -> None:
    client, provider, repository = make_m2_client()
    provider.memory_analysis = MemoryAnalysis(
        category=MemoryCategory.PEOPLE,
        person_name="Andy",
        relationship_to_user="university classmate",
        confidence=1.0,
    )

    with client:
        remembered = client.post(
            "/v1/commands/execute",
            json={"raw": "/remember Andy is my university classmate."},
        ).json()
        memory_id = remembered["memory"]["short_id"]
        listed = client.post(
            "/v1/commands/execute",
            json={"raw": "/memories Andy"},
        ).json()
        preview = client.post(
            "/v1/commands/execute",
            json={"raw": f"/forget {memory_id}"},
        ).json()
        before_confirm = client.post(
            "/v1/commands/execute",
            json={"raw": "/memories Andy"},
        ).json()
        deleted = client.post(
            "/v1/commands/execute",
            json={"raw": f"/forget {memory_id} confirm"},
        ).json()
        after_confirm = client.post(
            "/v1/commands/execute",
            json={"raw": "/memories Andy"},
        ).json()

    assert remembered["ok"] is True
    assert listed["memories"][0]["content"] == "Andy is my university classmate."
    assert preview["confirmation_required"] is True
    assert len(before_confirm["memories"]) == 1
    assert deleted["memory"]["status"] == "deleted"
    assert after_confirm["memories"] == []
    assert repository.list_memories() == []


def test_conversation_end_extracts_memory_and_repeated_fact_does_not_duplicate() -> None:
    client, provider, repository = make_m2_client()

    with client:
        conversation = client.post("/v1/conversations").json()
        sent = client.post(
            f"/v1/conversations/{conversation['id']}/messages",
            json={"content": "Anny and Larry argued yesterday."},
        ).json()
        provider.memory_candidates = [
            MemoryCandidate(
                category=MemoryCategory.RELATIONSHIPS,
                content="Anny and Larry argued yesterday.",
                person_name="Anny",
                confidence=0.95,
                source_message_ids=[sent["user_message"]["id"]],
            )
        ]
        first_end = client.post(f"/v1/conversations/{conversation['id']}/end").json()
        second_end = client.post(f"/v1/conversations/{conversation['id']}/end").json()

    assert len(first_end["memory_extraction"]["created"]) == 1
    assert second_end["memory_extraction"]["created"] == []
    assert len(provider.memory_extraction_requests) == 1
    assert second_end["conversation"]["memory_extraction_status"] == "completed"
    assert second_end["conversation"]["memory_extraction_attempts"] == 1
    assert len(repository.list_memories()) == 1


def test_ended_conversation_rejects_messages_with_conflict() -> None:
    client, _, _ = make_m2_client()

    with client:
        conversation = client.post("/v1/conversations").json()
        client.post(f"/v1/conversations/{conversation['id']}/end")
        response = client.post(
            f"/v1/conversations/{conversation['id']}/messages",
            json={"content": "Too late"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Conversation has ended"}


def test_failed_extraction_preserves_end_and_retries_deterministically() -> None:
    client, provider, _ = make_m2_client()

    with client:
        conversation = client.post("/v1/conversations").json()
        client.post(
            f"/v1/conversations/{conversation['id']}/messages",
            json={"content": "Remember this important fact."},
        )
        provider.memory_extraction_error = LLMTemporaryError("provider offline")
        failed = client.post(f"/v1/conversations/{conversation['id']}/end").json()
        provider.memory_extraction_error = None
        retried = client.post(f"/v1/conversations/{conversation['id']}/end").json()

    assert failed["conversation"]["ended_at"] is not None
    assert failed["memory_extraction"]["error"] == "provider offline"
    assert retried["conversation"]["memory_extraction_status"] == "completed"
    assert retried["conversation"]["memory_extraction_attempts"] == 2


def test_new_conversation_recovers_interrupted_session() -> None:
    client, provider, _ = make_m2_client()

    with client:
        interrupted = client.post("/v1/conversations").json()
        client.post(
            f"/v1/conversations/{interrupted['id']}/messages",
            json={"content": "A recoverable session fact."},
        )
        client.post("/v1/conversations")
        recovered = client.get(f"/v1/conversations/{interrupted['id']}").json()

    assert recovered["conversation"]["ended_at"] is not None
    assert recovered["conversation"]["memory_extraction_status"] == "completed"
    assert len(provider.memory_extraction_requests) == 1


def test_new_conversation_receives_relevant_memory_context() -> None:
    client, provider, _ = make_m2_client()
    provider.memory_analysis = MemoryAnalysis(
        category=MemoryCategory.PEOPLE,
        person_name="Andy",
        relationship_to_user="university classmate",
        confidence=0.95,
    )

    with client:
        client.post(
            "/v1/commands/execute",
            json={"raw": "/remember Andy is my university classmate."},
        )
        conversation = client.post("/v1/conversations").json()
        client.post(
            f"/v1/conversations/{conversation['id']}/messages",
            json={"content": "Do you remember who Andy is?"},
        )

    chat_request = provider.chat_requests[-1]
    assert chat_request.messages[0].role == "system"
    assert "Andy is my university classmate" in chat_request.messages[0].content
    assert "internal memory IDs" in chat_request.messages[0].content
