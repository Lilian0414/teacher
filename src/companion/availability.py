from dataclasses import dataclass
from datetime import datetime, timedelta

from companion.clock import Clock, system_clock
from companion.persistence.repositories import AvailabilityRepository, decode_dt
from companion.schemas.availability import AvailabilitySnapshot, AvailabilityState


@dataclass(frozen=True)
class OverrideRequest:
    state: AvailabilityState
    duration: timedelta | None
    source: str = "terminal"


class AvailabilityService:
    def __init__(
        self,
        *,
        repository: AvailabilityRepository,
        clock: Clock = system_clock,
        user_id: str = "default",
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._user_id = user_id

    def snapshot(self) -> AvailabilitySnapshot:
        now = self._clock()
        override = self._repository.latest_active(user_id=self._user_id, now=now)
        if override is None:
            latest = self._repository.latest(user_id=self._user_id)
            if latest is not None and latest.state == AvailabilityState.BUSY.value:
                expires_at = decode_dt(latest.expires_at) if latest.expires_at else None
                if expires_at is not None and expires_at <= now:
                    self._repository.add_override(
                        user_id=self._user_id,
                        state=AvailabilityState.AVAILABLE,
                        starts_at=now,
                        expires_at=None,
                        source="system",
                    )
            return AvailabilitySnapshot(
                state=AvailabilityState.AVAILABLE,
                source="default",
                expires_at=None,
                remaining_seconds=None,
            )

        expires_at = decode_dt(override.expires_at) if override.expires_at else None
        return AvailabilitySnapshot(
            state=AvailabilityState(override.state),
            source=override.source,
            expires_at=expires_at,
            remaining_seconds=self._remaining_seconds(now, expires_at),
        )

    def set_override(self, request: OverrideRequest) -> AvailabilitySnapshot:
        now = self._clock()
        if request.state == AvailabilityState.BUSY and request.duration is None:
            raise ValueError("busy override requires an expiration duration")

        current = self.snapshot()
        if current.state == AvailabilityState.DND and request.state not in {
            AvailabilityState.AVAILABLE,
            AvailabilityState.DND,
        }:
            return current

        expires_at = now + request.duration if request.duration else None
        self._repository.add_override(
            user_id=self._user_id,
            state=request.state,
            starts_at=now,
            expires_at=expires_at,
            source=request.source,
        )
        return self.snapshot()

    def clear_override(self) -> AvailabilitySnapshot:
        return self.set_override(
            OverrideRequest(
                state=AvailabilityState.AVAILABLE,
                duration=None,
                source="terminal",
            )
        )

    def apply_low_priority_state(self, state: AvailabilityState) -> AvailabilitySnapshot:
        current = self.snapshot()
        if current.state == AvailabilityState.DND:
            return current
        return self.set_override(
            OverrideRequest(state=state, duration=timedelta(minutes=5), source="system")
        )

    @staticmethod
    def _remaining_seconds(now: datetime, expires_at: datetime | None) -> int | None:
        if expires_at is None:
            return None
        return max(0, int((expires_at - now).total_seconds()))
