from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from companion.api.dependencies import (
    get_availability_service,
    get_learning_service,
    get_llm_provider,
    get_speech_transcriber,
)
from companion.availability import AvailabilityService
from companion.learning import LearningRepository, LearningService
from companion.learning.schemas import LearningKind
from companion.main import create_app
from companion.persistence.database import Base, make_engine
from companion.persistence.models import LearningAttempt, LearningItem
from companion.persistence.repositories import AvailabilityRepository
from companion.providers.fake import FakeLLMProvider


class FakeTranscriber:
    async def transcribe(self, audio: bytes, *, content_type: str) -> str:
        assert audio == b"wave"
        assert content_type == "audio/wav"
        return "I fell asleep."


def test_speech_transcription_endpoint_is_core_owned_and_non_mutating() -> None:
    app = create_app()
    app.dependency_overrides[get_speech_transcriber] = lambda: FakeTranscriber()

    with TestClient(app) as client:
        response = client.post(
            "/v1/speech/transcriptions", content=b"wave", headers={"content-type": "audio/wav"}
        )

    assert response.status_code == 200
    assert response.json() == {"transcript": "I fell asleep."}


def test_health_and_state_endpoints() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)

    def override_service() -> Generator[AvailabilityService, None, None]:
        yield AvailabilityService(
            repository=AvailabilityRepository(session),
            clock=lambda: now,
            user_id="default",
        )

    def override_learning() -> Generator[LearningService, None, None]:
        yield LearningService(
            repository=LearningRepository(session), clock=lambda: now, user_id="default"
        )

    app = create_app()
    app.dependency_overrides[get_availability_service] = override_service
    app.dependency_overrides[get_learning_service] = override_learning

    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        payload = client.get("/v1/state").json()

    assert payload["availability"] == "available"
    assert payload["override_expires_at"] is None
    assert payload["timezone"] == "Asia/Taipei"
    assert payload["due_review_count"] == 0


def test_unknown_command_response_is_deterministic() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)

    def override_service() -> Generator[AvailabilityService, None, None]:
        yield AvailabilityService(
            repository=AvailabilityRepository(session),
            clock=lambda: now,
            user_id="default",
        )

    app = create_app()
    app.dependency_overrides[get_availability_service] = override_service

    with TestClient(app) as client:
        payload = client.post("/v1/commands/execute", json={"raw": "/unknown hello"}).json()

    assert payload["ok"] is False
    assert payload["command"] == "unknown"
    assert "/busy <duration>" in payload["message"]


def test_due_review_count_reflects_pending_items() -> None:
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

    learning_service = LearningService(
        repository=LearningRepository(session), clock=lambda: now, user_id="default"
    )

    def override_learning() -> Generator[LearningService, None, None]:
        yield learning_service

    app = create_app()
    app.dependency_overrides[get_availability_service] = override_availability
    app.dependency_overrides[get_learning_service] = override_learning
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()

    with TestClient(app) as client:
        before = client.get("/v1/state").json()
        client.post(
            "/v1/commands/execute",
            json={"raw": "/hint 我不會說出軌"},
        )
        after = client.get("/v1/state").json()

    assert before["due_review_count"] == 0
    assert after["due_review_count"] == 1


def test_review_hint_does_not_mutate_learning_persistence() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    repository = LearningRepository(session)
    learning_service = LearningService(repository=repository, clock=lambda: now)
    item = repository.upsert_item(
        user_id="default",
        prompt="original prompt",
        kind=LearningKind.PHRASE,
        accepted_answers=["original answer"],
        source_command="hint",
        now=now,
        first_review_at=now,
    )
    item_id = item.id

    app = create_app()
    app.dependency_overrides[get_learning_service] = lambda: learning_service
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()

    before_items = list(session.scalars(select(LearningItem)))
    before_state = [
        (
            existing.id,
            existing.prompt,
            existing.accepted_answers,
            existing.source_command,
            existing.stage,
            existing.next_review_at,
            existing.created_at,
            existing.updated_at,
        )
        for existing in before_items
    ]
    before_attempts = list(session.scalars(select(LearningAttempt)))

    with TestClient(app) as client:
        response = client.post(f"/v1/review/{item_id}/hint")

    session.expire_all()
    after_items = list(session.scalars(select(LearningItem)))
    after_state = [
        (
            existing.id,
            existing.prompt,
            existing.accepted_answers,
            existing.source_command,
            existing.stage,
            existing.next_review_at,
            existing.created_at,
            existing.updated_at,
        )
        for existing in after_items
    ]
    assert response.status_code == 200
    assert response.json()["hints"]
    assert after_state == before_state
    assert list(session.scalars(select(LearningAttempt))) == before_attempts == []


def test_command_api_changes_availability() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)

    def override_service() -> Generator[AvailabilityService, None, None]:
        yield AvailabilityService(
            repository=AvailabilityRepository(session),
            clock=lambda: now,
            user_id="default",
        )

    def override_learning() -> Generator[LearningService, None, None]:
        yield LearningService(
            repository=LearningRepository(session), clock=lambda: now, user_id="default"
        )

    app = create_app()
    app.dependency_overrides[get_availability_service] = override_service
    app.dependency_overrides[get_learning_service] = override_learning

    with TestClient(app) as client:
        busy = client.post("/v1/commands/execute", json={"raw": "/busy 1h30m"}).json()
        state_after_busy = client.get("/v1/state").json()
        dnd = client.post("/v1/commands/execute", json={"raw": "/dnd"}).json()
        available = client.post("/v1/commands/execute", json={"raw": "/available"}).json()

    assert busy["availability"]["state"] == "busy"
    assert state_after_busy["availability"] == "busy"
    assert state_after_busy["remaining_seconds"] == int(
        timedelta(hours=1, minutes=30).total_seconds()
    )
    assert dnd["availability"]["state"] == "dnd"
    assert available["availability"]["state"] == "available"
