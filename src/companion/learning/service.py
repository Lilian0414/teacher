from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from companion.clock import Clock, system_clock
from companion.input_policy import is_materially_han
from companion.learning.errors import (
    LearningItemNotDueError,
    LearningItemNotFoundError,
    ReviewInputLanguageError,
)
from companion.learning.grading import AnswerGradingPolicy, LocalGrade
from companion.learning.normalization import normalize_learning_text
from companion.learning.repository import LearningRepository
from companion.learning.schemas import (
    LearningErrorType,
    LearningItemSchema,
    LearningKind,
    LearningSignalCandidate,
    LearningSignalConfidence,
    LearningSignalObservation,
    LearningSignalReason,
    LearningSignalRequest,
    ReviewQuestion,
    ReviewResult,
)
from companion.learning.signal_policy import validate_learning_signal
from companion.persistence.models import LearningItem
from companion.persistence.repositories import decode_dt
from companion.providers.errors import LLMProviderError
from companion.providers.schemas import (
    LanguageHelpMode,
    LanguageHelpResponse,
    SemanticGradeRequest,
    SemanticGradeVerdict,
    contains_cjk,
)

if TYPE_CHECKING:
    from companion.providers.protocols import LLMProvider

REVIEW_INTERVAL_DAYS = (1, 3, 7, 14, 30)
CONVERSATION_FIRST_REVIEW_DELAY = timedelta(days=1)
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
        captured_at = self._clock()
        item = self._repository.upsert_item(
            user_id=self._user_id,
            prompt=prompt,
            kind=kind,
            accepted_answers=answers,
            source_command=mode.value,
            now=captured_at,
            # Explicit assistance is intentionally reviewable immediately.
            first_review_at=captured_at,
        )
        return self._schema(item)

    def capture_conversation_signal(
        self,
        *,
        request: LearningSignalRequest,
        candidate: LearningSignalCandidate,
        observation: LearningSignalObservation | None = None,
    ) -> LearningItemSchema | None:
        if self._is_chitchat(request.user_content):
            return None
        if (
            candidate.source_conversation_id != request.conversation_id
            or candidate.source_user_message_id != request.user_message_id
            or candidate.source_assistant_message_id != request.assistant_message_id
        ):
            return None
        if candidate.reason == LearningSignalReason.CORRECTION:
            if observation is None or not self._valid_correction_evidence(request, observation):
                return None
        validated = validate_learning_signal(
            prompt=candidate.review_prompt, accepted_answers=candidate.accepted_answers
        )
        if validated is None:
            return None
        captured_at = self._clock()
        occurrence = self._repository.capture_occurrence(
            user_id=self._user_id,
            prompt=validated.prompt,
            kind=candidate.kind,
            accepted_answers=validated.accepted_answers,
            conversation_id=request.conversation_id,
            user_message_id=request.user_message_id,
            assistant_message_id=request.assistant_message_id,
            acceptance_reason=candidate.reason.value,
            now=captured_at,
            first_review_at=captured_at + CONVERSATION_FIRST_REVIEW_DELAY,
        )
        item = self._repository.get_item(occurrence.learning_item_id, user_id=self._user_id)
        assert item is not None
        return self._schema(item)

    @staticmethod
    def _valid_correction_evidence(
        request: LearningSignalRequest, observation: LearningSignalObservation
    ) -> bool:
        if (
            observation.error_type == LearningErrorType.NONE
            or observation.confidence != LearningSignalConfidence.HIGH
        ):
            return False
        source = normalize_learning_text(observation.source_excerpt)
        correction = normalize_learning_text(observation.correction)
        user_content = normalize_learning_text(request.user_content)
        return bool(source and correction and source != correction and source in user_content)

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

    def review_prompt(self, item_id: str) -> str:
        """Return an item's prompt without changing its review state."""
        item = self._repository.get_item(item_id, user_id=self._user_id)
        if item is None:
            raise LearningItemNotFoundError(item_id)
        return item.prompt

    def due_count(self) -> int:
        return self._repository.due_count(user_id=self._user_id, now=self._clock())

    def answer_deterministically(
        self, *, item_id: str, answer: str, position: int = 1, total: int = 1
    ) -> ReviewResult:
        """Grade without network access (kept for local/internal deterministic callers)."""
        if is_materially_han(answer):
            raise ReviewInputLanguageError
        now = self._clock()
        item = self._repository.get_item(item_id, user_id=self._user_id)
        if item is None:
            raise LearningItemNotFoundError(item_id)
        if decode_dt(item.next_review_at) > now:
            raise LearningItemNotDueError(item_id)
        accepted = self._repository.answers(item)
        correct = self._grading_policy.grade(answer, accepted)
        return self._record_resolved_answer(
            item=item,
            answer=answer,
            accepted=accepted,
            correct=correct,
            now=now,
            position=position,
            total=total,
        )

    async def answer(
        self,
        *,
        item_id: str,
        answer: str,
        llm_provider: LLMProvider,
        position: int = 1,
        total: int = 1,
    ) -> ReviewResult:
        if is_materially_han(answer):
            raise ReviewInputLanguageError
        now = self._clock()
        item = self._repository.get_item(item_id, user_id=self._user_id)
        if item is None:
            raise LearningItemNotFoundError(item_id)
        if decode_dt(item.next_review_at) > now:
            raise LearningItemNotDueError(item_id)
        accepted = self._repository.answers(item)
        local_grade = self._grading_policy.deterministic_grade(answer, accepted)
        if local_grade == LocalGrade.CORRECT:
            correct = True
        elif local_grade == LocalGrade.INCORRECT:
            correct = False
        else:
            try:
                decision = await llm_provider.grade_review_answer(
                    SemanticGradeRequest(
                        review_prompt=item.prompt,
                        kind=item.kind,
                        accepted_answers=accepted,
                        submitted_answer=answer,
                    )
                )
            except LLMProviderError:
                return self._deferred_result(
                    item=item,
                    answer=answer,
                    accepted=accepted,
                    position=position,
                    total=total,
                )
            if decision.verdict == SemanticGradeVerdict.CORRECT:
                if decision.target_preserved is not True:
                    return self._deferred_result(
                        item=item,
                        answer=answer,
                        accepted=accepted,
                        position=position,
                        total=total,
                    )
                correct = True
            elif decision.verdict == SemanticGradeVerdict.INCORRECT:
                correct = False
            else:
                return self._deferred_result(
                    item=item,
                    answer=answer,
                    accepted=accepted,
                    position=position,
                    total=total,
                )
        return self._record_resolved_answer(
            item=item,
            answer=answer,
            accepted=accepted,
            correct=correct,
            now=now,
            position=position,
            total=total,
        )

    def _record_resolved_answer(
        self,
        *,
        item: LearningItem,
        answer: str,
        accepted: list[str],
        correct: bool,
        now: datetime,
        position: int,
        total: int,
    ) -> ReviewResult:
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

    def _deferred_result(
        self,
        *,
        item: LearningItem,
        answer: str,
        accepted: list[str],
        position: int,
        total: int,
    ) -> ReviewResult:
        return ReviewResult(
            correct=None,
            prompt=item.prompt,
            submitted_answer=answer.strip(),
            accepted_answers=accepted,
            stage=item.stage,
            next_review_at=decode_dt(item.next_review_at),
            next_question=self._question(item, position=position, total=total),
            complete=False,
            grading_deferred=True,
            feedback="I couldn't grade that confidently — try another wording.",
        )

    @staticmethod
    def _reviewable_answers(
        *,
        mode: LanguageHelpMode,
        prompt: str,
        response: LanguageHelpResponse,
    ) -> list[str]:
        if mode == LanguageHelpMode.HINT:
            return [answer for answer in response.accepted_answers if "___" not in answer]
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
