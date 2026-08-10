from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import get_availability_service
from companion.availability import AvailabilityService
from companion.main import create_app
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository


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

    app = create_app()
    app.dependency_overrides[get_availability_service] = override_service

    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        payload = client.get("/v1/state").json()

    assert payload["availability"] == "available"
    assert payload["override_expires_at"] is None
    assert payload["timezone"] == "Asia/Taipei"


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

    app = create_app()
    app.dependency_overrides[get_availability_service] = override_service

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
