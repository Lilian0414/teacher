from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import get_proactive_service
from companion.availability import AvailabilityService
from companion.conversation import ConversationRepository, ConversationService
from companion.learning import LearningRepository, LearningService
from companion.learning.schemas import (
    LearningKind,
    LearningSignalCandidate,
    LearningSignalReason,
    LearningSignalRequest,
)
from companion.main import create_app
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from companion.proactive import (
    InvitationDecision,
    ProactiveCheckRequest,
    ProactiveRepository,
    ProactiveService,
)
from companion.settings import Settings
from tests.support import RecordingLLMProvider


class ProactiveSignalProvider(RecordingLLMProvider):
    async def extract_learning_signal(
        self, request: LearningSignalRequest
    ) -> LearningSignalCandidate:
        self.learning_signal_requests.append(request)
        return LearningSignalCandidate(
            source_conversation_id=request.conversation_id,
            source_user_message_id=request.user_message_id,
            source_assistant_message_id=request.assistant_message_id,
            kind=LearningKind.EXPRESSION,
            review_prompt="I went home",
            accepted_answers=["I went home"],
            reason=LearningSignalReason.CORRECTION,
        )


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


@pytest.mark.asyncio
async def test_conversation_practice_reuses_occurrence_and_completion_is_idempotent() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    settings = Settings(timezone="UTC", proactive_conversation_idle_seconds=0)
    learning_repository = LearningRepository(session)
    learning = LearningService(repository=learning_repository, clock=lambda: now)
    service = ProactiveService(
        repository=ProactiveRepository(session),
        availability=AvailabilityService(
            repository=AvailabilityRepository(session), clock=lambda: now
        ),
        learning=learning,
        settings=settings,
        clock=lambda: now,
    )
    invitation = service.check(ProactiveCheckRequest(idle_seconds=0, can_present=True))
    assert invitation is not None
    service.respond(invitation.id, InvitationDecision.START)

    conversation_service = ConversationService(
        repository=ConversationRepository(session),
        llm_provider=ProactiveSignalProvider(),
        learning_service=learning,
        clock=lambda: now,
    )
    conversation = conversation_service.create_conversation()
    turn = await conversation_service.send_user_message(
        conversation_id=conversation.id, content="I goed home"
    )
    assert turn.assistant_message is not None
    occurrence = learning_repository.occurrences()[0]

    completed = service.finalize_practice(
        invitation.id,
        conversation_id=conversation.id,
        user_message_id=turn.user_message.id,
        assistant_message_id=turn.assistant_message.id,
    )
    retried = service.finalize_practice(
        invitation.id,
        conversation_id=conversation.id,
        user_message_id=turn.user_message.id,
        assistant_message_id=turn.assistant_message.id,
    )

    assert completed.status == "completed"
    assert completed.outcome == "learning_signal_captured"
    assert completed.learning_occurrence_id == occurrence.id
    assert completed.learning_item_id == occurrence.learning_item_id
    assert retried == completed
    assert learning.due_count() == 1
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
