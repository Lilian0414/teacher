from datetime import timedelta

from companion.clock import Clock, system_clock
from companion.learning.errors import LearningItemNotDueError, LearningItemNotFoundError
from companion.learning.normalization import normalize_learning_text
from companion.learning.repository import LearningRepository
from companion.learning.schemas import (
    LearningItemSchema,
    LearningKind,
    ReviewQuestion,
    ReviewResult,
)
from companion.persistence.models import LearningItem
from companion.persistence.repositories import decode_dt
from companion.providers.schemas import LanguageHelpMode, LanguageHelpResponse, contains_cjk

REVIEW_INTERVAL_DAYS = (1, 3, 7, 14, 30)


class LearningService:
    def __init__(
        self,
        *,
        repository: LearningRepository,
        clock: Clock = system_clock,
        user_id: str = "default",
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._user_id = user_id

    def capture_assistance(
        self,
        *,
        mode: LanguageHelpMode,
        prompt: str,
        response: LanguageHelpResponse,
    ) -> LearningItemSchema | None:
        if mode == LanguageHelpMode.SAY:
            return None
        kind = LearningKind.PHRASE if mode == LanguageHelpMode.HINT else LearningKind.EXPRESSION
        answers = self._reviewable_answers(mode=mode, prompt=prompt, response=response)
        if not answers:
            return None
        item = self._repository.upsert_item(
            user_id=self._user_id,
            prompt=prompt,
            kind=kind,
            accepted_answers=answers,
            source_command=mode.value,
            now=self._clock(),
        )
        return self._schema(item)

    def first_due(self) -> ReviewQuestion | None:
        items = self._repository.due_items(user_id=self._user_id, now=self._clock(), limit=1)
        return self._question(items[0]) if items else None

    def answer(self, *, item_id: str, answer: str) -> ReviewResult:
        now = self._clock()
        item = self._repository.get_item(item_id, user_id=self._user_id)
        if item is None:
            raise LearningItemNotFoundError(item_id)
        if decode_dt(item.next_review_at) > now:
            raise LearningItemNotDueError(item_id)
        accepted = self._repository.answers(item)
        normalized_answer = normalize_learning_text(answer)
        correct = bool(normalized_answer) and any(
            normalized_answer == normalize_learning_text(candidate) for candidate in accepted
        )
        stage_after = item.stage + 1 if correct else 0
        interval_index = min(max(stage_after - 1, 0), len(REVIEW_INTERVAL_DAYS) - 1)
        next_review_at = now + timedelta(days=REVIEW_INTERVAL_DAYS[interval_index])
        self._repository.record_attempt(
            item=item,
            submitted_answer=answer,
            correct=correct,
            stage_after=stage_after,
            next_review_at=next_review_at,
            attempted_at=now,
        )
        next_question = self.first_due()
        return ReviewResult(
            correct=correct,
            accepted_answers=accepted,
            stage=stage_after,
            next_review_at=next_review_at,
            next_question=next_question,
            complete=next_question is None,
        )

    @staticmethod
    def _reviewable_answers(
        *,
        mode: LanguageHelpMode,
        prompt: str,
        response: LanguageHelpResponse,
    ) -> list[str]:
        if mode == LanguageHelpMode.HINT:
            return response.hints
        answers = [
            value
            for value in [response.natural_expression, response.correction, *response.alternatives]
            if value
        ]
        if not answers and not contains_cjk(prompt):
            answers.append(prompt)
        return answers

    @staticmethod
    def _question(item: LearningItem) -> ReviewQuestion:
        return ReviewQuestion(
            id=item.id,
            prompt=item.prompt,
            kind=LearningKind(item.kind),
        )

    def _schema(self, item: LearningItem) -> LearningItemSchema:
        return LearningItemSchema(
            id=item.id,
            prompt=item.prompt,
            kind=LearningKind(item.kind),
            accepted_answers=self._repository.answers(item),
            source_command=item.source_command,
            stage=item.stage,
            next_review_at=decode_dt(item.next_review_at),
            created_at=decode_dt(item.created_at),
            updated_at=decode_dt(item.updated_at),
        )
