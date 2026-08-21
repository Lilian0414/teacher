from collections.abc import Generator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from companion.api.dependencies import get_proactive_service
from companion.availability import AvailabilityService
from companion.learning import LearningRepository, LearningService
from companion.main import create_app
from companion.persistence.database import Base, make_engine
from companion.persistence.repositories import AvailabilityRepository
from companion.proactive import ProactiveRepository, ProactiveService
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
