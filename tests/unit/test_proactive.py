from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from companion.availability import AvailabilityService, OverrideRequest
from companion.learning import LearningRepository, LearningService
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from companion.proactive import (
    InvitationConflictError,
    InvitationDecision,
    InvitationKind,
    ProactiveCheckRequest,
    ProactiveRepository,
    ProactiveService,
)
from companion.schemas.availability import AvailabilityState
from companion.settings import Settings


def make_service() -> tuple[
    ProactiveService,
    ProactiveRepository,
    list[datetime],
    AvailabilityService,
]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = [datetime(2026, 8, 21, 12, tzinfo=UTC)]
    availability = AvailabilityService(
        repository=AvailabilityRepository(session), clock=lambda: now[0]
    )
    repository = ProactiveRepository(session)
    settings = Settings(
        timezone="UTC",
        proactive_review_idle_seconds=10,
        proactive_conversation_idle_seconds=20,
        proactive_snooze_minutes=30,
        proactive_accept_cooldown_minutes=60,
        proactive_daily_limit=2,
    )
    service = ProactiveService(
        repository=repository,
        availability=availability,
        learning=LearningService(repository=LearningRepository(session), clock=lambda: now[0]),
        settings=settings,
        clock=lambda: now[0],
    )
    return service, repository, now, availability


def test_settings_and_request_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(proactive_daily_limit=0)
    with pytest.raises(ValidationError):
        ProactiveCheckRequest(idle_seconds=-1, can_present=True)


def test_check_suppression_pending_stability_and_atomic_decision() -> None:
    service, repository, now, availability = make_service()
    assert service.check(ProactiveCheckRequest(idle_seconds=1799, can_present=True)) is None
    invitation = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert invitation is not None and invitation.kind == InvitationKind.CONVERSATION
    repeated = service.check(ProactiveCheckRequest(idle_seconds=999, can_present=True))
    assert repeated is not None and repeated.id == invitation.id

    response = service.respond(invitation.id, InvitationDecision.SNOOZE)
    assert response.invitation.suppress_until == now[0] + timedelta(minutes=30)
    with pytest.raises(InvitationConflictError):
        service.respond(invitation.id, InvitationDecision.START)
    assert repository.delivery_count("default", now[0].date()) == 1

    now[0] += timedelta(minutes=31)
    availability.set_override(OverrideRequest(AvailabilityState.BUSY, timedelta(hours=1)))
    assert service.check(ProactiveCheckRequest(idle_seconds=999, can_present=True)) is None


def test_dismissal_and_daily_limit_use_local_date() -> None:
    service, _, now, _ = make_service()
    first = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert first is not None
    service.respond(first.id, InvitationDecision.DISMISS_TODAY)
    now[0] = datetime(2026, 8, 22, 0, tzinfo=UTC)
    second = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert second is not None and second.starter_key == "week-highlight"
    service.respond(second.id, InvitationDecision.SNOOZE)
    now[0] += timedelta(minutes=31)
    third = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert third is not None and third.starter_key == "recent-learning"
    service.respond(third.id, InvitationDecision.SNOOZE)
    now[0] += timedelta(minutes=31)
    fourth = service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True))
    assert fourth is not None
    service.respond(fourth.id, InvitationDecision.SNOOZE)
    now[0] += timedelta(minutes=31)
    assert service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True)) is None
