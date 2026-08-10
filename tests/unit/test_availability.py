from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from companion.availability import AvailabilityService, OverrideRequest
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from companion.schemas.availability import AvailabilityState


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current = self.current + delta


def make_service(clock: MutableClock) -> AvailabilityService:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    return AvailabilityService(
        repository=AvailabilityRepository(session),
        clock=clock,
        user_id="default",
    )


def test_default_state_is_available() -> None:
    clock = MutableClock(datetime(2026, 7, 19, 12, tzinfo=UTC))
    service = make_service(clock)

    assert service.snapshot().state == AvailabilityState.AVAILABLE


def test_busy_override_expires_without_waiting() -> None:
    clock = MutableClock(datetime(2026, 7, 19, 12, tzinfo=UTC))
    service = make_service(clock)

    service.set_override(
        OverrideRequest(state=AvailabilityState.BUSY, duration=timedelta(minutes=1))
    )
    assert service.snapshot().state == AvailabilityState.BUSY

    clock.advance(timedelta(minutes=1, seconds=1))
    assert service.snapshot().state == AvailabilityState.AVAILABLE


def test_expired_busy_writes_available_state_to_database() -> None:
    clock = MutableClock(datetime(2026, 7, 19, 12, tzinfo=UTC))
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    repository = AvailabilityRepository(session)
    service = AvailabilityService(repository=repository, clock=clock, user_id="default")

    service.set_override(
        OverrideRequest(state=AvailabilityState.BUSY, duration=timedelta(minutes=1))
    )
    clock.advance(timedelta(minutes=1, seconds=1))

    assert service.snapshot().state == AvailabilityState.AVAILABLE
    latest = repository.latest(user_id="default")
    assert latest is not None
    assert latest.state == AvailabilityState.AVAILABLE.value
    assert latest.expires_at is None


def test_dnd_is_not_overwritten_by_lower_priority_state() -> None:
    clock = MutableClock(datetime(2026, 7, 19, 12, tzinfo=UTC))
    service = make_service(clock)

    service.set_override(OverrideRequest(state=AvailabilityState.DND, duration=None))
    service.apply_low_priority_state(AvailabilityState.AVAILABLE)
    service.set_override(
        OverrideRequest(state=AvailabilityState.BUSY, duration=timedelta(minutes=1))
    )

    assert service.snapshot().state == AvailabilityState.DND


def test_available_clears_dnd() -> None:
    clock = MutableClock(datetime(2026, 7, 19, 12, tzinfo=UTC))
    service = make_service(clock)

    service.set_override(OverrideRequest(state=AvailabilityState.DND, duration=None))
    service.set_override(OverrideRequest(state=AvailabilityState.AVAILABLE, duration=None))

    assert service.snapshot().state == AvailabilityState.AVAILABLE


def test_dnd_does_not_expire() -> None:
    clock = MutableClock(datetime(2026, 7, 19, 12, tzinfo=UTC))
    service = make_service(clock)

    service.set_override(OverrideRequest(state=AvailabilityState.DND, duration=None))
    clock.advance(timedelta(days=30))

    snapshot = service.snapshot()
    assert snapshot.state == AvailabilityState.DND
    assert snapshot.expires_at is None


def test_busy_requires_expiration_duration() -> None:
    clock = MutableClock(datetime(2026, 7, 19, 12, tzinfo=UTC))
    service = make_service(clock)

    try:
        service.set_override(OverrideRequest(state=AvailabilityState.BUSY, duration=None))
    except ValueError as exc:
        assert "requires" in str(exc)
    else:
        raise AssertionError("busy without duration should fail")
