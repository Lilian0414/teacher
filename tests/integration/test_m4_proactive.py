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
from companion.persistence.models import LearningOccurrence
from companion.persistence.repositories import AvailabilityRepository
from companion.proactive import (
    InvitationDecision,
    ProactiveCheckRequest,
    ProactiveRepository,
    ProactiveService,
)
from companion.schemas.conversation import MessageRole
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
    conversation = ConversationRepository(session).create_conversation(
        user_id="default", started_at=now
    )
    foreign = ConversationRepository(session).create_conversation(
        user_id="someone-else", started_at=now
    )

    def override() -> Generator[ProactiveService, None, None]:
        yield service

    app = create_app()
    app.dependency_overrides[get_proactive_service] = override
    with TestClient(app) as client:
        first = client.post(
            "/v1/proactive/check", json={"idle_seconds": 1800, "can_present": True}
        ).json()["invitation"]
        repeated = client.post(
            "/v1/proactive/check", json={"idle_seconds": 9999, "can_present": True}
        ).json()["invitation"]
        missing_conversation = client.post(
            f"/v1/proactive/invitations/{first['id']}/respond",
            json={"decision": "start"},
        )
        wrong_conversation = client.post(
            f"/v1/proactive/invitations/{first['id']}/respond",
            json={"decision": "start", "conversation_id": foreign.id},
        )
        accepted = client.post(
            f"/v1/proactive/invitations/{first['id']}/respond",
            json={"decision": "start", "conversation_id": conversation.id},
        )
        duplicate = client.post(
            f"/v1/proactive/invitations/{first['id']}/respond",
            json={"decision": "start", "conversation_id": conversation.id},
        )

    assert repeated["id"] == first["id"]
    assert missing_conversation.status_code == 422
    assert wrong_conversation.status_code == 422
    assert accepted.status_code == 200
    assert accepted.json()["invitation"]["conversation_id"] == conversation.id
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
    conversation_service = ConversationService(
        repository=ConversationRepository(session),
        llm_provider=ProactiveSignalProvider(),
        learning_service=learning,
        clock=lambda: now,
    )
    conversation = conversation_service.create_conversation()
    invitation = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert invitation is not None
    service.respond(invitation.id, InvitationDecision.START, conversation.id)
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
    invitation = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert invitation is not None
    conversation = ConversationRepository(session).create_conversation(
        user_id="default", started_at=now
    )
    service.respond(invitation.id, InvitationDecision.START, conversation.id)

    with pytest.raises(ValueError, match="bound conversation"):
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


def test_start_requires_owned_conversation_and_binds_atomically() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    repository = ProactiveRepository(session)
    service = ProactiveService(
        repository=repository,
        availability=AvailabilityService(
            repository=AvailabilityRepository(session), clock=lambda: now
        ),
        learning=LearningService(repository=LearningRepository(session), clock=lambda: now),
        settings=Settings(
            timezone="UTC", proactive_conversation_idle_seconds=0, proactive_daily_limit=10
        ),
        clock=lambda: now,
    )
    invitation = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert invitation is not None

    with pytest.raises(ValueError, match="required"):
        service.respond(invitation.id, InvitationDecision.START)
    assert repository.get(invitation.id, "default").status == "pending"  # type: ignore[union-attr]

    foreign = ConversationRepository(session).create_conversation(
        user_id="someone-else", started_at=now
    )
    with pytest.raises(ValueError, match="current user"):
        service.respond(invitation.id, InvitationDecision.START, foreign.id)
    assert repository.get(invitation.id, "default").status == "pending"  # type: ignore[union-attr]

    owned = ConversationRepository(session).create_conversation(user_id="default", started_at=now)
    accepted = service.respond(invitation.id, InvitationDecision.START, owned.id).invitation
    assert accepted.status == "accepted"
    assert accepted.conversation_id == owned.id
    assert service.check(ProactiveCheckRequest(idle_seconds=999, can_present=True)) is None


@pytest.mark.asyncio
async def test_restart_reconciliation_is_exact_deterministic_and_idempotent() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    clock = [datetime(2026, 8, 21, 12, tzinfo=UTC)]
    repository = ProactiveRepository(session)
    learning_repository = LearningRepository(session)
    learning = LearningService(repository=learning_repository, clock=lambda: clock[0])
    service = ProactiveService(
        repository=repository,
        availability=AvailabilityService(
            repository=AvailabilityRepository(session), clock=lambda: clock[0]
        ),
        learning=learning,
        settings=Settings(
            timezone="UTC", proactive_conversation_idle_seconds=0, proactive_daily_limit=10
        ),
        clock=lambda: clock[0],
    )
    conversations = ConversationService(
        repository=ConversationRepository(session),
        llm_provider=RecordingLLMProvider(),
        learning_service=learning,
        clock=lambda: clock[0],
    )

    no_answer_conversation = conversations.create_conversation()
    no_answer = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert no_answer is not None
    service.respond(no_answer.id, InvitationDecision.START, no_answer_conversation.id)
    assert service.reconcile_accepted_practices()[0].status == "abandoned"
    assert session.query(LearningOccurrence).count() == 0

    clock[0] += timedelta(minutes=61)
    partial_conversation = conversations.create_conversation()
    partial = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert partial is not None
    service.respond(partial.id, InvitationDecision.START, partial_conversation.id)
    user = ConversationRepository(session).add_message(
        conversation_id=partial_conversation.id,
        role=MessageRole.USER,
        content="saved once",
        language="en",
        source="terminal",
        created_at=clock[0],
    )
    assert service.reconcile_accepted_practices()[0].status == "abandoned"
    partial_row = repository.get(partial.id, "default")
    assert partial_row is not None and partial_row.user_message_id is None
    assert session.get(type(user), user.id) is not None
    assert session.query(LearningOccurrence).count() == 0

    clock[0] += timedelta(minutes=61)
    complete_conversation = conversations.create_conversation()
    complete = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert complete is not None
    service.respond(complete.id, InvitationDecision.START, complete_conversation.id)
    turn = await conversations.send_user_message(
        conversation_id=complete_conversation.id, content="one exact answer"
    )
    assert turn.assistant_message is not None
    reconciled = service.reconcile_accepted_practices()[0]
    assert reconciled.status == "completed"
    assert reconciled.conversation_id == complete_conversation.id
    assert reconciled.user_message_id == turn.user_message.id
    assert reconciled.assistant_message_id == turn.assistant_message.id
    assert reconciled.outcome == "completed_not_evaluated"
    assert service.reconcile_accepted_practices() == []
    assert session.query(LearningOccurrence).count() == 0

    clock[0] += timedelta(days=1, minutes=61)
    ambiguous_conversation = conversations.create_conversation()
    ambiguous = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert ambiguous is not None
    service.respond(ambiguous.id, InvitationDecision.START, ambiguous_conversation.id)
    await conversations.send_user_message(
        conversation_id=ambiguous_conversation.id, content="first pair"
    )
    await conversations.send_user_message(
        conversation_id=ambiguous_conversation.id, content="second pair"
    )
    ambiguous_result = service.reconcile_accepted_practices()[0]
    assert ambiguous_result.status == "abandoned"
    assert ambiguous_result.user_message_id is None
    assert ambiguous_result.assistant_message_id is None
    assert session.query(LearningOccurrence).count() == 0
