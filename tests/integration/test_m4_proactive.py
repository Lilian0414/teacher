from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import get_proactive_service
from companion.availability import AvailabilityService
from companion.conversation.repository import ConversationRepository
from companion.learning import LearningRepository, LearningService
from companion.learning.schemas import LearningKind
from companion.main import create_app
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from companion.proactive import (
    InvitationDecision,
    ProactiveCheckRequest,
    ProactiveRepository,
    ProactiveService,
)
from companion.schemas.conversation import MessageRole
from companion.settings import Settings


def test_proactive_http_flow_is_persistent_and_safe_for_duplicate_decisions() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    service = ProactiveService(
        repository=ProactiveRepository(session),
        availability=AvailabilityService(
            repository=AvailabilityRepository(session), clock=lambda: now
        ),
        learning=LearningService(repository=LearningRepository(session), clock=lambda: now),
        settings=Settings(
            timezone="UTC",
            proactive_conversation_idle_seconds=0,
        ),
        clock=lambda: now,
    )

    def override() -> Generator[ProactiveService, None, None]:
        yield service

    app = create_app()
    app.dependency_overrides[get_proactive_service] = override
    with TestClient(app) as client:
        first = client.post(
            "/v1/proactive/check", json={"idle_seconds": 0, "can_present": True}
        ).json()["invitation"]
        repeated = client.post(
            "/v1/proactive/check", json={"idle_seconds": 99, "can_present": True}
        ).json()["invitation"]
        accepted = client.post(
            f"/v1/proactive/invitations/{first['id']}/respond",
            json={"decision": "start"},
        )
        duplicate = client.post(
            f"/v1/proactive/invitations/{first['id']}/respond",
            json={"decision": "start"},
        )

    assert repeated["id"] == first["id"]
    assert accepted.status_code == 200
    assert accepted.json()["conversation_starter"] == first["starter_prompt"]
    assert duplicate.status_code == 409


def test_conversation_practice_reuses_occurrence_and_completion_is_idempotent() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    settings = Settings(timezone="UTC", proactive_conversation_idle_seconds=0)
    learning_repository = LearningRepository(session)
    service = ProactiveService(
        repository=ProactiveRepository(session),
        availability=AvailabilityService(
            repository=AvailabilityRepository(session), clock=lambda: now
        ),
        learning=LearningService(repository=learning_repository, clock=lambda: now),
        settings=settings,
        clock=lambda: now,
    )
    invitation = service.check(ProactiveCheckRequest(idle_seconds=0, can_present=True))
    assert invitation is not None
    service.respond(invitation.id, InvitationDecision.START)

    conversations = ConversationRepository(session)
    conversation = conversations.create_conversation(user_id=settings.user_id, started_at=now)
    user_message = conversations.add_message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="I goed home",
        language="en",
        source="terminal",
        created_at=now,
    )
    assistant_message = conversations.add_message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="You can say: I went home.",
        language="en",
        source="terminal",
        created_at=now,
    )
    occurrence = learning_repository.capture_occurrence(
        user_id=settings.user_id,
        prompt="I went home",
        kind=LearningKind.EXPRESSION,
        accepted_answers=["I went home"],
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        acceptance_reason="correction",
        now=now,
    )

    completed = service.finalize_practice(
        invitation.id,
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
    )
    retried = service.finalize_practice(
        invitation.id,
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
    )

    assert completed.status == "completed"
    assert completed.outcome == "learning_signal_captured"
    assert completed.learning_occurrence_id == occurrence.id
    assert completed.learning_item_id == occurrence.learning_item_id
    assert retried == completed
    assert service._learning.due_count() == 1
    service._clock = lambda: now + timedelta(minutes=61)
    later = service.check(ProactiveCheckRequest(idle_seconds=9999, can_present=True))
    assert later is not None
    assert later.kind == "review"


def test_started_practice_can_be_abandoned_but_not_completed_with_foreign_evidence() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    service = ProactiveService(
        repository=ProactiveRepository(session),
        availability=AvailabilityService(
            repository=AvailabilityRepository(session), clock=lambda: now
        ),
        learning=LearningService(repository=LearningRepository(session), clock=lambda: now),
        settings=Settings(timezone="UTC", proactive_conversation_idle_seconds=0),
        clock=lambda: now,
    )
    invitation = service.check(ProactiveCheckRequest(idle_seconds=0, can_present=True))
    assert invitation is not None
    service.respond(invitation.id, InvitationDecision.START)

    with pytest.raises(ValueError, match="current user"):
        service.finalize_practice(
            invitation.id,
            conversation_id="foreign",
            user_message_id="foreign-user",
            assistant_message_id="foreign-assistant",
        )

    abandoned = service.abandon_practice(invitation.id)
    assert abandoned.status == "abandoned"
    assert abandoned.outcome == "abandoned"
    assert service.abandon_practice(invitation.id) == abandoned
    assert service._learning.due_count() == 0
