import json
from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from companion.learning.errors import LearningItemNotDueError
from companion.learning.normalization import merge_answers, normalize_learning_text
from companion.learning.schemas import LearningKind
from companion.persistence.models import LearningAttempt, LearningItem
from companion.persistence.repositories import encode_dt


class LearningRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_item(
        self,
        *,
        user_id: str,
        prompt: str,
        kind: LearningKind,
        accepted_answers: list[str],
        source_command: str,
        now: datetime,
    ) -> LearningItem:
        normalized_prompt = normalize_learning_text(prompt)
        item = self._session.scalars(
            select(LearningItem).where(
                LearningItem.user_id == user_id,
                LearningItem.normalized_prompt == normalized_prompt,
                LearningItem.kind == kind.value,
            )
        ).one_or_none()
        encoded_now = encode_dt(now)
        if item is None:
            item = LearningItem(
                id=str(uuid4()),
                user_id=user_id,
                prompt=prompt.strip(),
                normalized_prompt=normalized_prompt,
                kind=kind.value,
                accepted_answers=json.dumps(merge_answers([], accepted_answers)),
                source_command=source_command,
                stage=0,
                next_review_at=encoded_now,
                created_at=encoded_now,
                updated_at=encoded_now,
            )
            self._session.add(item)
        else:
            item.prompt = prompt.strip()
            item.accepted_answers = json.dumps(merge_answers(self.answers(item), accepted_answers))
            item.source_command = source_command
            item.next_review_at = min(item.next_review_at, encoded_now)
            item.updated_at = encoded_now
        self._session.commit()
        self._session.refresh(item)
        return item

    def get_item(self, item_id: str, *, user_id: str) -> LearningItem | None:
        return self._session.scalar(
            select(LearningItem).where(LearningItem.id == item_id, LearningItem.user_id == user_id)
        )

    def due_items(self, *, user_id: str, now: datetime, limit: int = 20) -> list[LearningItem]:
        return list(
            self._session.scalars(
                select(LearningItem)
                .where(
                    LearningItem.user_id == user_id,
                    LearningItem.next_review_at <= encode_dt(now),
                )
                .order_by(
                    LearningItem.next_review_at.asc(),
                    LearningItem.created_at.asc(),
                    LearningItem.id.asc(),
                )
                .limit(limit)
            )
        )

    def due_count(self, *, user_id: str, now: datetime) -> int:
        return (
            self._session.scalar(
                select(func.count(LearningItem.id)).where(
                    LearningItem.user_id == user_id,
                    LearningItem.next_review_at <= encode_dt(now),
                )
            )
            or 0
        )

    def record_attempt(
        self,
        *,
        item: LearningItem,
        submitted_answer: str,
        correct: bool,
        stage_after: int,
        next_review_at: datetime,
        attempted_at: datetime,
    ) -> LearningAttempt:
        stage_before = item.stage
        expected_due_at = item.next_review_at
        attempt = LearningAttempt(
            id=str(uuid4()),
            learning_item_id=item.id,
            submitted_answer=submitted_answer.strip(),
            correct=correct,
            stage_before=stage_before,
            stage_after=stage_after,
            attempted_at=encode_dt(attempted_at),
        )
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(LearningItem)
                .where(
                    LearningItem.id == item.id,
                    LearningItem.stage == stage_before,
                    LearningItem.next_review_at == expected_due_at,
                )
                .values(
                    stage=stage_after,
                    next_review_at=encode_dt(next_review_at),
                    updated_at=encode_dt(attempted_at),
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            self._session.rollback()
            raise LearningItemNotDueError(item.id)
        self._session.add(attempt)
        self._session.commit()
        self._session.refresh(item)
        return attempt

    def attempts_for(self, item_id: str) -> list[LearningAttempt]:
        return list(
            self._session.scalars(
                select(LearningAttempt)
                .where(LearningAttempt.learning_item_id == item_id)
                .order_by(LearningAttempt.attempted_at, LearningAttempt.id)
            )
        )

    @staticmethod
    def answers(item: LearningItem) -> list[str]:
        decoded = json.loads(item.accepted_answers)
        return [str(answer) for answer in decoded]
