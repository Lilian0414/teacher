from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from companion.learning import (
    LearningContextBuilder,
    LearningItemNotDueError,
    LearningRepository,
    LearningService,
)
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

    current[0] += timedelta(days=1)
    incorrect = service.answer(item_id=item.id, answer="sleepy")
    assert incorrect.correct is False
    assert incorrect.stage == 0
    assert incorrect.next_review_at == current[0] + timedelta(days=1)


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
