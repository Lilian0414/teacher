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
    ProactiveReason,
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
    assert service.check(ProactiveCheckRequest(idle_seconds=19, can_present=True)) is None
    invitation = service.check(ProactiveCheckRequest(idle_seconds=20, can_present=True))
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


def test_status_explains_eligibility_without_delivering() -> None:
    service, repository, _, availability = make_service()
    request = ProactiveCheckRequest(idle_seconds=0, can_present=True)

    waiting = service.status(request)
    assert waiting.reason == ProactiveReason.INSUFFICIENT_IDLE
    assert waiting.idle_threshold_seconds == 20
    assert waiting.idle_remaining_seconds == 20
    assert waiting.next_kind == InvitationKind.CONVERSATION
    assert waiting.uses_legacy_policy is True
    assert repository.delivery_count("default", datetime(2026, 8, 21).date()) == 0

    assert service.status(request.model_copy(update={"can_present": False})).reason == (
        ProactiveReason.UI_CANNOT_PRESENT
    )
    availability.set_override(OverrideRequest(AvailabilityState.BUSY, timedelta(hours=1)))
    busy = service.status(request)
    assert busy.reason == ProactiveReason.BUSY
    assert busy.not_before == busy.availability_expires_at
    assert busy.availability_expires_at is not None
    availability.set_override(OverrideRequest(AvailabilityState.DND, None))
    assert service.status(request).reason == ProactiveReason.DND


def test_status_preserves_pending_snooze_and_daily_limit_order() -> None:
    service, _, now, _ = make_service()
    request = ProactiveCheckRequest(idle_seconds=999, can_present=True)
    assert service.status(request).reason == ProactiveReason.ELIGIBLE
    invitation = service.check(request)
    assert invitation is not None
    assert service.status(request).reason == ProactiveReason.PENDING_INVITATION
    service.respond(invitation.id, InvitationDecision.SNOOZE)
    snoozed = service.status(request)
    assert snoozed.reason == ProactiveReason.SNOOZED
    assert snoozed.not_before == now[0] + timedelta(minutes=30)

    now[0] += timedelta(minutes=31)
    second = service.check(request)
    assert second is not None
    service.respond(second.id, InvitationDecision.SNOOZE)
    now[0] += timedelta(minutes=31)
    limited = service.status(request)
    assert limited.reason == ProactiveReason.DAILY_LIMIT
    assert (limited.daily_delivery_count, limited.daily_delivery_limit) == (2, 2)


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
    assert service.check(ProactiveCheckRequest(idle_seconds=1800, can_present=True)) is None
