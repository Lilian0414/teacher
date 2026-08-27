from datetime import UTC, datetime, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import get_preferences_service
from companion.availability import AvailabilityService, OverrideRequest
from companion.learning import LearningRepository, LearningService
from companion.main import create_app
from companion.persistence.database import Base, make_engine
from companion.persistence.models import LearnerPreferences
from companion.persistence.repositories import AvailabilityRepository
from companion.preferences import (
    CorrectionStyle,
    PreferencesRepository,
    PreferencesService,
    PreferencesUpdate,
    ProactiveCadence,
)
from companion.proactive import ProactiveCheckRequest, ProactiveRepository, ProactiveService
from companion.proactive.schemas import InvitationDecision
from companion.schemas.availability import AvailabilityState
from companion.settings import Settings


def test_preferences_defaults_partial_update_reset_and_restart() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    service = PreferencesService(PreferencesRepository(session))
    assert service.read().onboarded is False
    assert service.read().correction_style == "normal"

    service.update(
        PreferencesUpdate(
            correction_style=CorrectionStyle.INTENSIVE,
            sound_enabled=False,
            active_hours_start=time(8),
            active_hours_end=time(22),
            quiet_hours_start=time(12),
            quiet_hours_end=time(13),
        )
    )
    restarted = PreferencesService(PreferencesRepository(Session(engine)))
    assert restarted.read().correction_style == "intensive"
    assert restarted.read().proactive_cadence == "normal"
    assert restarted.read().sound_enabled is False
    reset = restarted.reset()
    assert reset.correction_style == "normal"
    assert reset.active_hours_start is None
    assert reset.active_hours_end is None
    assert reset.quiet_hours_start is None
    assert reset.quiet_hours_end is None
    row = Session(engine).get(LearnerPreferences, "default")
    assert row is not None
    assert row.active_hours_start is None
    assert row.active_hours_end is None
    assert row.quiet_hours_start is None
    assert row.quiet_hours_end is None
    assert restarted.read().onboarded is True


def test_onboarding_offer_is_persisted_once_and_can_be_explicitly_restarted() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_run = PreferencesService(PreferencesRepository(Session(engine)))

    assert first_run.offer_onboarding() is True
    assert first_run.read().onboarded is True

    restarted = PreferencesService(PreferencesRepository(Session(engine)))
    assert restarted.offer_onboarding() is False
    restarted.restart_onboarding()
    assert restarted.offer_onboarding() is True
    assert restarted.offer_onboarding() is False


def test_preferences_http_api_uses_core_service() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    service = PreferencesService(PreferencesRepository(Session(engine)))
    app = create_app()
    app.dependency_overrides[get_preferences_service] = lambda: service
    with TestClient(app) as client:
        assert client.get("/v1/preferences").json()["onboarded"] is False
        updated = client.patch(
            "/v1/preferences", json={"proactive_cadence": "rare"}
        ).json()
        assert updated["proactive_cadence"] == "rare"
        assert updated["correction_style"] == "normal"


def test_timezone_windows_and_cadence_suppress_without_weakening_availability() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    preferences = PreferencesService(PreferencesRepository(session))
    preferences.update(
        PreferencesUpdate(
            proactive_cadence=ProactiveCadence.FREQUENT,
            active_hours_start=time(8),
            active_hours_end=time(22),
            quiet_hours_start=time(12),
            quiet_hours_end=time(13),
        )
    )
    now = [datetime(2026, 8, 27, 3, 30, tzinfo=UTC)]  # 11:30 Asia/Taipei
    availability = AvailabilityService(
        repository=AvailabilityRepository(session), clock=lambda: now[0]
    )
    service = ProactiveService(
        repository=ProactiveRepository(session),
        availability=availability,
        learning=LearningService(repository=LearningRepository(session)),
        settings=Settings(timezone="Asia/Taipei"),
        preferences=preferences,
        clock=lambda: now[0],
    )
    assert service.check(ProactiveCheckRequest(idle_seconds=899, can_present=True)) is None
    invitation = service.check(ProactiveCheckRequest(idle_seconds=900, can_present=True))
    assert invitation is not None

    service.respond(invitation.id, InvitationDecision.DISMISS_TODAY)
    now[0] = datetime(2026, 8, 27, 4, 30, tzinfo=UTC)  # quiet 12:30 local
    assert service.check(ProactiveCheckRequest(idle_seconds=9999, can_present=True)) is None
    availability.set_override(
        OverrideRequest(
            state=AvailabilityState.BUSY, duration=timedelta(minutes=30), source="test"
        )
    )
    now[0] = datetime(2026, 8, 27, 5, 30, tzinfo=UTC)
    assert service.check(ProactiveCheckRequest(idle_seconds=9999, can_present=True)) is None
