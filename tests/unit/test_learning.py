from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from companion.learning import (
    LearningContextBuilder,
    LearningItemNotDueError,
    LearningKind,
    LearningRepository,
    LearningService,
)
from companion.learning.grading import AnswerGradingPolicy
from companion.learning.normalization import normalize_learning_text
from companion.persistence.database import Base, make_engine
from companion.providers.schemas import LanguageHelpMode, LanguageHelpResponse


def make_learning() -> tuple[LearningRepository, LearningService, list[datetime]]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    current = [datetime(2026, 8, 10, 12, tzinfo=UTC)]
    repository = LearningRepository(session)
    service = LearningService(repository=repository, clock=lambda: current[0])
    return repository, service, current


def test_normalization_and_repeated_capture_merge_without_duplicate() -> None:
    repository, service, current = make_learning()
    first = service.capture_assistance(
        mode=LanguageHelpMode.HELP,
        prompt="  How   are you? ",
        response=LanguageHelpResponse(natural_expression="How are you?"),
    )
    current[0] += timedelta(hours=1)
    second = service.capture_assistance(
        mode=LanguageHelpMode.HELP,
        prompt="how are you!",
        response=LanguageHelpResponse(alternatives=["How's it going?"]),
    )

    assert normalize_learning_text(" HOW   are you?! ") == "how are you"
    assert first is not None and second is not None
    assert first.id == second.id
    assert second.accepted_answers == ["How are you?", "How's it going?"]
    assert len(repository.due_items(user_id="default", now=current[0])) == 1


@pytest.mark.parametrize("mode", [LanguageHelpMode.HELP, LanguageHelpMode.HINT])
def test_repeated_assistance_preserves_existing_review_schedule(mode: LanguageHelpMode) -> None:
    repository, service, current = make_learning()
    response = (
        LanguageHelpResponse(natural_expression="I am exhausted.")
        if mode == LanguageHelpMode.HELP
        else LanguageHelpResponse(hints=["exhausted"])
    )
    item = service.capture_assistance(mode=mode, prompt="我很累", response=response)
    assert item is not None
    reviewed = service.answer(item_id=item.id, answer="exhausted")
    scheduled_at = reviewed.next_review_at

    current[0] += timedelta(hours=1)
    repeated = service.capture_assistance(mode=mode, prompt="我很累", response=response)

    assert repeated is not None and repeated.id == item.id
    assert repeated.next_review_at == scheduled_at


def test_repeated_conversation_occurrences_preserve_first_and_review_due_times() -> None:
    repository, service, current = make_learning()
    first_due = current[0] + timedelta(days=1)
    first = repository.capture_occurrence(
        user_id="default",
        prompt="How can I say I am tired?",
        kind=LearningKind.EXPRESSION,
        accepted_answers=["I am tired."],
        conversation_id="conversation-1",
        user_message_id="user-1",
        assistant_message_id="assistant-1",
        acceptance_reason="useful_expression",
        now=current[0],
        first_review_at=first_due,
    )

    current[0] += timedelta(hours=6)
    second = repository.capture_occurrence(
        user_id="default",
        prompt="How can I say I am tired?",
        kind=LearningKind.EXPRESSION,
        accepted_answers=["I'm tired."],
        conversation_id="conversation-2",
        user_message_id="user-2",
        assistant_message_id="assistant-2",
        acceptance_reason="useful_expression",
        now=current[0],
        first_review_at=current[0] + timedelta(days=1),
    )
    item = repository.get_item(first.learning_item_id, user_id="default")

    assert second.learning_item_id == first.learning_item_id
    assert len(repository.occurrences()) == 2
    assert item is not None and item.next_review_at == first_due.isoformat()
    assert repository.answers(item) == ["I am tired.", "I'm tired."]

    current[0] = first_due
    reviewed = service.answer(item_id=item.id, answer="I am tired.")
    current[0] += timedelta(hours=1)
    repository.capture_occurrence(
        user_id="default",
        prompt="How can I say I am tired?",
        kind=LearningKind.EXPRESSION,
        accepted_answers=["I feel tired."],
        conversation_id="conversation-3",
        user_message_id="user-3",
        assistant_message_id="assistant-3",
        acceptance_reason="useful_expression",
        now=current[0],
        first_review_at=current[0] + timedelta(days=1),
    )
    item = repository.get_item(item.id, user_id="default")

    assert item is not None and item.next_review_at == reviewed.next_review_at.isoformat()
    assert len(repository.occurrences()) == 3


def test_help_and_hint_have_isolated_answers_and_review_progress() -> None:
    repository, service, current = make_learning()
    first = service.capture_assistance(
        mode=LanguageHelpMode.HELP,
        prompt="我今天很累",
        response=LanguageHelpResponse(natural_expression="I am tired today."),
    )
    second = service.capture_assistance(
        mode=LanguageHelpMode.HINT,
        prompt=" 我今天很累！ ",
        response=LanguageHelpResponse(hints=["tired", "exhausted"]),
    )
    assert first is not None and second is not None
    assert first.id != second.id
    assert first.accepted_answers == ["I am tired today."]
    assert second.accepted_answers == ["tired", "exhausted"]
    question = service.first_due()
    assert question is not None
    assert (question.position, question.total, question.remaining) == (1, 2, 2)
    stored = repository.get_item(question.id, user_id="default")
    assert stored is not None
    result = service.answer(
        item_id=first.id,
        answer="tired",
        position=question.position,
        total=question.total,
    )
    assert result.correct is False
    assert result.stage == 0
    assert result.next_question is not None
    assert (
        result.next_question.position,
        result.next_question.total,
        result.next_question.remaining,
    ) == (2, 2, 1)
    hint = repository.get_item(second.id, user_id="default")
    expression = repository.get_item(first.id, user_id="default")
    assert hint is not None and expression is not None
    assert hint.stage == 0
    assert expression.stage == 0
    assert hint.next_review_at == current[0].isoformat()
    assert expression.next_review_at == (current[0] + timedelta(days=1)).isoformat()


def test_capture_rules_include_english_original_and_exclude_say_or_empty_chinese() -> None:
    _, service, _ = make_learning()
    english = service.capture_assistance(
        mode=LanguageHelpMode.HELP,
        prompt="How did you know?",
        response=LanguageHelpResponse(notes_zh="自然且正確"),
    )
    say = service.capture_assistance(
        mode=LanguageHelpMode.SAY,
        prompt="你好",
        response=LanguageHelpResponse(natural_expression="Hello"),
    )
    empty = service.capture_assistance(
        mode=LanguageHelpMode.HELP,
        prompt="你好",
        response=LanguageHelpResponse(notes_zh="沒有答案"),
    )

    assert english is not None and english.accepted_answers == ["How did you know?"]
    assert say is None
    assert empty is None


def test_review_grading_schedule_and_stale_answer_protection() -> None:
    repository, service, current = make_learning()
    item = service.capture_assistance(
        mode=LanguageHelpMode.HINT,
        prompt="我想說很累",
        response=LanguageHelpResponse(hints=["worn out", "exhausted"]),
    )
    assert item is not None

    correct = service.answer(item_id=item.id, answer="  WORN   OUT! ")
    assert correct.correct is True
    assert correct.stage == 1
    assert correct.next_review_at == current[0] + timedelta(days=1)
    assert len(repository.attempts_for(item.id)) == 1
    with pytest.raises(LearningItemNotDueError):
        service.answer(item_id=item.id, answer="worn out")
    assert len(repository.attempts_for(item.id)) == 1

    current[0] += timedelta(days=1)
    incorrect = service.answer(item_id=item.id, answer="sleepy")
    assert incorrect.correct is False
    assert incorrect.stage == 0
    assert incorrect.next_review_at == current[0] + timedelta(days=1)


@pytest.mark.parametrize(
    ("accepted", "submitted"),
    [("I am tired.", "I'm tired."), ("I'm tired.", "I am tired.")],
)
def test_safe_contraction_variants_advance_and_record_once(
    accepted: str, submitted: str
) -> None:
    repository, service, current = make_learning()
    item = service.capture_assistance(
        mode=LanguageHelpMode.HELP,
        prompt="累",
        response=LanguageHelpResponse(natural_expression=accepted),
    )
    assert item is not None

    result = service.answer(item_id=item.id, answer=submitted)

    assert result.correct is True
    assert result.stage == 1
    assert result.next_review_at == current[0] + timedelta(days=1)
    attempts = repository.attempts_for(item.id)
    assert len(attempts) == 1
    assert attempts[0].correct is True


def test_grading_policy_preserves_exact_alternates_and_rejects_unsupported_forms() -> None:
    policy = AnswerGradingPolicy()

    assert policy.grade("  WORN   OUT! ", ["exhausted", "worn out"])
    assert not policy.grade("He's finished.", ["He has finished."])
    assert not policy.grade("I am sleepy.", ["I am tired."])


def test_grading_failure_happens_before_learning_state_is_persisted() -> None:
    class FailingPolicy(AnswerGradingPolicy):
        def grade(self, submitted_answer: str, accepted_answers: Sequence[str]) -> bool:
            raise RuntimeError("grading failed")

    repository, _, current = make_learning()
    service = LearningService(
        repository=repository,
        clock=lambda: current[0],
        grading_policy=FailingPolicy(),
    )
    item = service.capture_assistance(
        mode=LanguageHelpMode.HELP,
        prompt="累",
        response=LanguageHelpResponse(natural_expression="I am tired."),
    )
    assert item is not None

    with pytest.raises(RuntimeError, match="grading failed"):
        service.answer(item_id=item.id, answer="I'm tired.")

    stored = repository.get_item(item.id, user_id="default")
    assert stored is not None
    assert stored.stage == 0
    assert stored.next_review_at == current[0].isoformat()
    assert repository.attempts_for(item.id) == []


def test_interval_caps_at_thirty_days_and_context_is_bounded() -> None:
    repository, service, current = make_learning()
    assert LearningContextBuilder(repository, limit=1).build(current[0]) is None
    item = service.capture_assistance(
        mode=LanguageHelpMode.HELP,
        prompt="累",
        response=LanguageHelpResponse(natural_expression="I am tired."),
    )
    assert item is not None
    for days in [1, 3, 7, 14, 30, 30]:
        result = service.answer(item_id=item.id, answer="I am tired")
        assert result.next_review_at == current[0] + timedelta(days=days)
        current[0] = result.next_review_at

    context = LearningContextBuilder(repository, limit=1).build(current[0])
    assert context is not None
    assert "Due learning goals" in context
    assert "Prompts:" in context
    assert "Accepted answers:" in context


def test_learning_item_and_attempt_persist_across_sessions(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'learning.sqlite3'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    with Session(engine) as session:
        first_repository = LearningRepository(session)
        first_service = LearningService(repository=first_repository, clock=lambda: now)
        item = first_service.capture_assistance(
            mode=LanguageHelpMode.HELP,
            prompt="早安",
            response=LanguageHelpResponse(natural_expression="Good morning."),
        )
        assert item is not None
        first_service.answer(item_id=item.id, answer="Good morning")

    with Session(engine) as session:
        restarted = LearningRepository(session)
        stored = restarted.get_item(item.id, user_id="default")
        attempts = restarted.attempts_for(item.id)

    assert stored is not None and stored.stage == 1
    assert len(attempts) == 1 and attempts[0].correct is True
