from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Select, select
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
            completed_at=None,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def get(self, user_message_id: str) -> LearningSignalProcessing | None:
        return self._session.get(LearningSignalProcessing, user_message_id)

    def recoverable(self, *, limit: int = 5) -> list[LearningSignalProcessing]:
        statement: Select[tuple[LearningSignalProcessing]] = (
            select(LearningSignalProcessing)
            .where(
                LearningSignalProcessing.retryable.is_(True),
                LearningSignalProcessing.attempts < MAX_ATTEMPTS,
                LearningSignalProcessing.status.in_(("pending", "failed")),
            )
            .order_by(LearningSignalProcessing.created_at)
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    async def process(self, row: LearningSignalProcessing, *, now: datetime) -> None:
        if row.status in {"completed", "no_candidate"} or not row.retryable:
            return
        user = self._session.get(Message, row.user_message_id)
        assistant = self._session.get(Message, row.assistant_message_id)
        if user is None or assistant is None:
            self._finish(row, now=now, status="failed", retryable=False, detail="missing turn")
            return
        row.attempts += 1
        row.last_attempted_at = encode_dt(now)
        row.status = "pending"
        row.status_detail = None
        self._session.commit()
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
                now=now,
                status="completed" if item is not None else "no_candidate",
                retryable=False,
                detail=None,
            )
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
            self._finish(row, now=now, status="failed", retryable=retryable, detail=detail)

    def _finish(
        self,
        row: LearningSignalProcessing,
        *,
        now: datetime,
        status: str,
        retryable: bool,
        detail: str | None,
    ) -> None:
        row.status = status
        row.retryable = retryable
        row.status_detail = detail
        row.completed_at = encode_dt(now) if status in TERMINAL_STATUSES and not retryable else None
        self._session.commit()
