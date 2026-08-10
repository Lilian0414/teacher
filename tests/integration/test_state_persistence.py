from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from companion.availability import AvailabilityService, OverrideRequest
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from companion.schemas.availability import AvailabilityState


def test_availability_state_persists_across_service_instances(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'companion.sqlite3'}"
    engine = make_engine(database_url)
    Base.metadata.create_all(bind=engine)
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)

    with Session(engine) as session:
        first_service = AvailabilityService(
            repository=AvailabilityRepository(session),
            clock=lambda: now,
            user_id="default",
        )
        first_service.set_override(
            OverrideRequest(state=AvailabilityState.BUSY, duration=timedelta(minutes=30))
        )

    with Session(engine) as session:
        restarted_service = AvailabilityService(
            repository=AvailabilityRepository(session),
            clock=lambda: now + timedelta(minutes=5),
            user_id="default",
        )
        snapshot = restarted_service.snapshot()

    assert snapshot.state == AvailabilityState.BUSY
    assert snapshot.remaining_seconds == 1500
