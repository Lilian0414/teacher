import re
from datetime import timedelta

from companion.clock import Clock, system_clock
from companion.learning.errors import LearningItemNotDueError, LearningItemNotFoundError
from companion.learning.grading import AnswerGradingPolicy
from companion.learning.normalization import normalize_learning_text
from companion.learning.repository import LearningRepository
from companion.learning.schemas import (
    LearningItemSchema,
    LearningKind,
    LearningSignalCandidate,
    LearningSignalRequest,
    ReviewQuestion,
    ReviewResult,
)
from companion.persistence.models import LearningItem
from companion.persistence.repositories import decode_dt
from companion.providers.schemas import LanguageHelpMode, LanguageHelpResponse, contains_cjk

REVIEW_INTERVAL_DAYS = (1, 3, 7, 14, 30)
CHITCHAT = re.compile(
    r"^(?:"
    r"(?:hi|hello|hey)(?:[ ,]+(?:there|how(?: are you|'s it going)))?"
    r"|good (?:morning|afternoon|evening|night)"
    r"|how(?: are you|'s it going)"
    r"|thanks(?: a lot)?|thank you(?: very much)?"
    r")$"
)


class LearningService:
    def __init__(
        self,
        *,
        repository: LearningRepository,
        clock: Clock = system_clock,
        user_id: str = "default",
        grading_policy: AnswerGradingPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._user_id = user_id
        self._grading_policy = grading_policy or AnswerGradingPolicy()

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

    def capture_conversation_signal(
        self, *, request: LearningSignalRequest, candidate: LearningSignalCandidate
    ) -> LearningItemSchema | None:
        if self._is_chitchat(request.user_content):
            return None
        if (
            candidate.source_conversation_id != request.conversation_id
            or candidate.source_user_message_id != request.user_message_id
            or candidate.source_assistant_message_id != request.assistant_message_id
        ):
            return None
        prompt = candidate.review_prompt.strip()
        answers = [answer.strip() for answer in candidate.accepted_answers if answer.strip()]
        if (
            not self._is_reviewable(prompt)
            or not answers
            or any(not self._is_reviewable(answer) for answer in answers)
        ):
            return None
        occurrence = self._repository.capture_occurrence(
            user_id=self._user_id,
            prompt=prompt,
            kind=candidate.kind,
            accepted_answers=answers,
            conversation_id=request.conversation_id,
            user_message_id=request.user_message_id,
            assistant_message_id=request.assistant_message_id,
            acceptance_reason=candidate.reason.value,
            now=self._clock(),
        )
        item = self._repository.get_item(occurrence.learning_item_id, user_id=self._user_id)
        assert item is not None
        return self._schema(item)

    @staticmethod
    def _is_reviewable(value: str) -> bool:
        normalized = normalize_learning_text(value)
        return len(normalized) >= 3 and normalized not in {"hello", "hi", "hey", "thanks"}

    @staticmethod
    def _is_chitchat(value: str) -> bool:
        normalized = normalize_learning_text(value)
        return CHITCHAT.fullmatch(normalized) is not None

    def first_due(self) -> ReviewQuestion | None:
        items = self._repository.due_items(user_id=self._user_id, now=self._clock(), limit=1)
        return self._question(items[0], total=self.due_count()) if items else None

    def due_count(self) -> int:
        return self._repository.due_count(user_id=self._user_id, now=self._clock())

    def answer(
        self, *, item_id: str, answer: str, position: int = 1, total: int = 1
    ) -> ReviewResult:
        now = self._clock()
        item = self._repository.get_item(item_id, user_id=self._user_id)
        if item is None:
            raise LearningItemNotFoundError(item_id)
        if decode_dt(item.next_review_at) > now:
            raise LearningItemNotDueError(item_id)
        accepted = self._repository.answers(item)
        correct = self._grading_policy.grade(answer, accepted)
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
        next_items = self._repository.due_items(user_id=self._user_id, now=now, limit=1)
        remaining = self._repository.due_count(user_id=self._user_id, now=now)
        next_question = (
            self._question(
                next_items[0],
                position=position + 1,
                total=max(total, position + remaining),
                remaining=remaining,
            )
            if next_items
            else None
        )
        return ReviewResult(
            correct=correct,
            prompt=item.prompt,
            submitted_answer=answer.strip(),
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
    def _question(
        item: LearningItem,
        *,
        position: int = 1,
        total: int = 1,
        remaining: int | None = None,
    ) -> ReviewQuestion:
        return ReviewQuestion(
            id=item.id,
            prompt=item.prompt,
            kind=LearningKind(item.kind),
            position=position,
            total=total,
            remaining=total - position + 1 if remaining is None else remaining,
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
