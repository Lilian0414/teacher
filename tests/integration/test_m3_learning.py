from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import (
    get_availability_service,
    get_conversation_service,
    get_learning_service,
    get_llm_provider,
    get_memory_service,
)
from companion.availability import AvailabilityService
from companion.conversation import ConversationRepository, ConversationService
from companion.learning import LearningContextBuilder, LearningRepository, LearningService
from companion.main import create_app
from companion.memory import MemoryContextBuilder, MemoryRepository, MemoryService
from companion.memory.schemas import MemoryAnalysis, MemoryCategory
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from tests.support import RecordingLLMProvider


def make_m3_client() -> tuple[TestClient, RecordingLLMProvider, LearningRepository, list[datetime]]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    current = [datetime(2026, 8, 10, 12, tzinfo=UTC)]
    provider = RecordingLLMProvider()
    learning_repository = LearningRepository(session)
    memory_repository = MemoryRepository(session)
    conversation_repository = ConversationRepository(session)
    learning_service = LearningService(
        repository=learning_repository, clock=lambda: current[0], user_id="default"
    )
    conversation_service = ConversationService(
        repository=conversation_repository,
        llm_provider=provider,
        clock=lambda: current[0],
        memory_context_builder=MemoryContextBuilder(memory_repository, limit=5),
        learning_context_builder=LearningContextBuilder(learning_repository, limit=3),
    )
    memory_service = MemoryService(
        repository=memory_repository,
        conversation_repository=conversation_repository,
        llm_provider=provider,
        clock=lambda: current[0],
    )

    def availability() -> Generator[AvailabilityService, None, None]:
        yield AvailabilityService(
            repository=AvailabilityRepository(session), clock=lambda: current[0]
        )

    app = create_app()
    app.dependency_overrides[get_availability_service] = availability
    app.dependency_overrides[get_conversation_service] = lambda: conversation_service
    app.dependency_overrides[get_learning_service] = lambda: learning_service
    app.dependency_overrides[get_memory_service] = lambda: memory_service
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return TestClient(app), provider, learning_repository, current


def test_help_capture_review_progression_and_duplicate_submission() -> None:
    client, _, repository, _ = make_m3_client()
    with client:
        captured = client.post("/v1/commands/execute", json={"raw": "/help 我今天很累"}).json()
        started = client.post("/v1/commands/execute", json={"raw": "/review"}).json()
        item_id = started["review_question"]["id"]
        answered = client.post(
            f"/v1/review/{item_id}/answer",
            json={"answer": "Natural English for: 我今天很累"},
        )
        duplicate = client.post(
            f"/v1/review/{item_id}/answer",
            json={"answer": "Natural English for: 我今天很累"},
        )
        no_due = client.get("/v1/review").json()

    assert captured["learning_item"]["kind"] == "expression"
    assert "accepted_answers" not in started["review_question"]
    assert answered.json()["result"]["correct"] is True
    assert answered.json()["result"]["complete"] is True
    assert duplicate.status_code == 409
    assert no_due == {"question": None, "complete": True}
    assert len(repository.attempts_for(item_id)) == 1


def test_due_order_resume_and_say_exclusion() -> None:
    client, _, repository, current = make_m3_client()
    with client:
        first = client.post("/v1/commands/execute", json={"raw": "/hint 第一題"}).json()[
            "learning_item"
        ]
        current[0] += timedelta(seconds=1)
        second = client.post("/v1/commands/execute", json={"raw": "/hint 第二題"}).json()[
            "learning_item"
        ]
        conversation = client.post("/v1/conversations").json()
        client.post(
            "/v1/commands/execute",
            json={"raw": "/say 你好", "conversation_id": conversation["id"]},
        )
        started = client.get("/v1/review").json()
        answer = client.post(
            f"/v1/review/{first['id']}/answer", json={"answer": "cheat on someone"}
        ).json()
        resumed = client.post("/v1/commands/execute", json={"raw": "/review"}).json()

    assert started["question"]["id"] == first["id"]
    assert answer["result"]["next_question"]["id"] == second["id"]
    assert resumed["review_question"]["id"] == second["id"]
    assert len(repository.due_items(user_id="default", now=current[0])) == 1


def test_due_learning_and_life_memory_are_separate_conversation_contexts() -> None:
    client, provider, _, _ = make_m3_client()
    provider.memory_analysis = MemoryAnalysis(
        category=MemoryCategory.PEOPLE,
        person_name="Andy",
        relationship_to_user="classmate",
        confidence=1.0,
    )
    with client:
        client.post("/v1/commands/execute", json={"raw": "/remember Andy is my classmate."})
        client.post("/v1/commands/execute", json={"raw": "/help 我很累"})
        conversation = client.post("/v1/conversations").json()
        client.post(
            f"/v1/conversations/{conversation['id']}/messages",
            json={"content": "Tell me about Andy."},
        )
        memories = client.post("/v1/commands/execute", json={"raw": "/memories 我很累"}).json()

    system = provider.chat_requests[-1].messages[0].content
    assert "memories may be relevant" in system
    assert "Due learning goals" in system
    assert memories["memories"] == []
