from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import CursorResult, Select, or_, select, update
from sqlalchemy.orm import Session

from companion.learning.schemas import LearningSignalExtraction, LearningSignalRequest
from companion.learning.service import LearningService
from companion.persistence.models import LearningSignalProcessing, Message
from companion.persistence.repositories import encode_dt
from companion.providers.errors import LLMProviderError

if TYPE_CHECKING:
    from companion.providers.protocols import LLMProvider

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
TERMINAL_STATUSES = frozenset({"completed", "no_candidate", "failed"})
LEASE_DURATION = timedelta(minutes=5)


class LearningSignalProcessor:
    """Own durable, bounded, idempotent post-conversation signal processing."""

    def __init__(self, session: Session, provider: LLMProvider, learning: LearningService) -> None:
        self._session = session
        self._provider = provider
        self._learning = learning

    def enqueue(
        self, *, user: Message, assistant: Message, now: datetime
    ) -> LearningSignalProcessing:
        existing = self.get(user.id)
        if existing is not None:
            return existing
        row = LearningSignalProcessing(
            user_message_id=user.id,
            conversation_id=user.conversation_id,
            assistant_message_id=assistant.id,
            status="pending",
            attempts=0,
            retryable=True,
            status_detail=None,
            created_at=encode_dt(now),
            last_attempted_at=None,
            claim_token=None,
            lease_expires_at=None,
            completed_at=None,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def get(self, user_message_id: str) -> LearningSignalProcessing | None:
        return self._session.get(LearningSignalProcessing, user_message_id)

    def recoverable(
        self, *, now: datetime, limit: int = 5
    ) -> list[LearningSignalProcessing]:
        # A process may die after claiming its final attempt. Once that lease expires,
        # close it deterministically rather than leaving an unclaimable in-flight row.
        self._session.execute(
            update(LearningSignalProcessing)
            .where(
                LearningSignalProcessing.status == "in_flight",
                LearningSignalProcessing.retryable.is_(True),
                LearningSignalProcessing.attempts >= MAX_ATTEMPTS,
                LearningSignalProcessing.lease_expires_at <= encode_dt(now),
            )
            .values(
                status="failed",
                retryable=False,
                status_detail="extraction interrupted",
                claim_token=None,
                lease_expires_at=None,
                completed_at=encode_dt(now),
            )
        )
        self._session.commit()
        statement: Select[tuple[LearningSignalProcessing]] = (
            select(LearningSignalProcessing)
            .where(
                LearningSignalProcessing.retryable.is_(True),
                LearningSignalProcessing.attempts < MAX_ATTEMPTS,
                or_(
                    LearningSignalProcessing.status.in_(("pending", "failed")),
                    (
                        (LearningSignalProcessing.status == "in_flight")
                        & (LearningSignalProcessing.lease_expires_at <= encode_dt(now))
                    ),
                ),
            )
            .order_by(LearningSignalProcessing.created_at)
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    async def process(self, row: LearningSignalProcessing, *, now: datetime) -> None:
        claim_token = self._claim(row.user_message_id, now=now)
        if claim_token is None:
            return
        claimed_row = self._session.get(LearningSignalProcessing, row.user_message_id)
        assert claimed_row is not None
        row = claimed_row
        user = self._session.get(Message, row.user_message_id)
        assistant = self._session.get(Message, row.assistant_message_id)
        if user is None or assistant is None:
            self._finish(
                row, claim_token=claim_token, now=now, status="failed",
                retryable=False, detail="missing turn"
            )
            return
        request = LearningSignalRequest(
            conversation_id=row.conversation_id,
            user_message_id=user.id,
            assistant_message_id=assistant.id,
            user_content=user.content,
            assistant_content=assistant.content,
        )
        try:
            result = await self._provider.extract_learning_signal(request)
            item = None
            if isinstance(result, LearningSignalExtraction):
                item = self._learning.capture_conversation_signal(
                    request=request, candidate=result.candidate, observation=result.observation
                )
            elif result is not None:
                item = self._learning.capture_conversation_signal(request=request, candidate=result)
            self._finish(
                row,
                claim_token=claim_token,
                now=now,
                status="completed" if item is not None else "no_candidate",
                retryable=False,
                detail=None,
            )
        except asyncio.CancelledError:
            retryable = row.attempts < MAX_ATTEMPTS
            self._finish(
                row,
                claim_token=claim_token,
                now=now,
                status="failed",
                retryable=retryable,
                detail="CancelledError: extraction unavailable",
            )
            raise
        except Exception as exc:
            retryable = exc.retryable if isinstance(exc, LLMProviderError) else True
            retryable = retryable and row.attempts < MAX_ATTEMPTS
            detail = f"{type(exc).__name__}: extraction unavailable"
            logger.warning(
                "Learning-signal extraction failed for turn %s (%s, retryable=%s)",
                row.user_message_id,
                type(exc).__name__,
                retryable,
            )
            self._finish(
                row, claim_token=claim_token, now=now, status="failed",
                retryable=retryable, detail=detail
            )

    def _claim(self, user_message_id: str, *, now: datetime) -> str | None:
        token = str(uuid4())
        result = self._session.execute(
            update(LearningSignalProcessing)
            .where(
                LearningSignalProcessing.user_message_id == user_message_id,
                LearningSignalProcessing.retryable.is_(True),
                LearningSignalProcessing.attempts < MAX_ATTEMPTS,
                or_(
                    LearningSignalProcessing.status.in_(("pending", "failed")),
                    (
                        (LearningSignalProcessing.status == "in_flight")
                        & (LearningSignalProcessing.lease_expires_at <= encode_dt(now))
                    ),
                ),
            )
            .values(
                status="in_flight", attempts=LearningSignalProcessing.attempts + 1,
                last_attempted_at=encode_dt(now), claim_token=token,
                lease_expires_at=encode_dt(now + LEASE_DURATION), status_detail=None,
            )
        )
        assert isinstance(result, CursorResult)
        self._session.commit()
        return token if result.rowcount == 1 else None

    def _finish(
        self,
        row: LearningSignalProcessing,
        *,
        claim_token: str,
        now: datetime,
        status: str,
        retryable: bool,
        detail: str | None,
    ) -> None:
        self._session.execute(
            update(LearningSignalProcessing)
            .where(
                LearningSignalProcessing.user_message_id == row.user_message_id,
                LearningSignalProcessing.status == "in_flight",
                LearningSignalProcessing.claim_token == claim_token,
            )
            .values(
                status=status, retryable=retryable, status_detail=detail,
                claim_token=None, lease_expires_at=None,
                completed_at=(
                    encode_dt(now) if status in TERMINAL_STATUSES and not retryable else None
                ),
            )
        )
        self._session.commit()
