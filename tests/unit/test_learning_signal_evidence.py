import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from companion.learning.repository import LearningRepository
from companion.learning.schemas import (
    LearningErrorType,
    LearningKind,
    LearningSignalCandidate,
    LearningSignalConfidence,
    LearningSignalObservation,
    LearningSignalReason,
    LearningSignalRequest,
)
from companion.learning.service import LearningService
from companion.persistence.database import Base, make_engine


def _request(user_content: str) -> LearningSignalRequest:
    return LearningSignalRequest(
        conversation_id="conversation-1",
        user_message_id="user-1",
        assistant_message_id="assistant-1",
        user_content=user_content,
        assistant_content="Thanks for sharing.",
    )


@pytest.mark.parametrize(
    ("excerpt", "correction", "error_type", "confidence", "expected"),
    [
        ("sleep", "slept", LearningErrorType.VERB_TENSE, LearningSignalConfidence.HIGH, True),
        ("SLEEP!", "slept", LearningErrorType.VERB_TENSE, LearningSignalConfidence.HIGH, True),
        ("rest", "rested", LearningErrorType.VERB_TENSE, LearningSignalConfidence.HIGH, False),
        ("sleep", "sleep", LearningErrorType.VERB_TENSE, LearningSignalConfidence.HIGH, False),
        ("sleep", "slept", LearningErrorType.NONE, LearningSignalConfidence.HIGH, False),
        ("sleep", "slept", LearningErrorType.VERB_TENSE, LearningSignalConfidence.MEDIUM, False),
        ("sleep", "slept", LearningErrorType.VERB_TENSE, LearningSignalConfidence.LOW, False),
        ("sleep", "slept", LearningErrorType.OTHER_CORRECTION, LearningSignalConfidence.HIGH, True),
        ("sleep", "slept", LearningErrorType.VERB_TENSE, LearningSignalConfidence.HIGH, True),
        ("lee", "left", LearningErrorType.VERB_TENSE, LearningSignalConfidence.HIGH, False),
    ],
)
def test_correction_evidence_is_bounded_and_high_confidence(
    excerpt: str,
    correction: str,
    error_type: LearningErrorType,
    confidence: LearningSignalConfidence,
    expected: bool,
) -> None:
    observation = LearningSignalObservation(
        error_type=error_type,
        source_excerpt=excerpt,
        correction=correction,
        confidence=confidence,
    )

    assert LearningService._valid_correction_evidence(
        _request("I was tired, so I sleep!"), observation
    ) is expected


def test_offline_eval_fixture_exercises_candidate_null_capture_behavior() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "learning_signal_eval.json"
    cases: list[dict[str, Any]] = json.loads(fixture.read_text())
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repository = LearningRepository(session)
        service = LearningService(repository=repository)
        for index, case in enumerate(cases):
            request = _request(case["input"]).model_copy(
                update={
                    "conversation_id": f"conversation-{index}",
                    "user_message_id": f"user-{index}",
                    "assistant_message_id": f"assistant-{index}",
                }
            )
            evidence = case["observation"]
            observation = LearningSignalObservation.model_validate(evidence)
            before = len(repository.occurrences())

            item = service.capture_conversation_signal(
                request=request, candidate=None, observation=observation
            )

            created = len(repository.occurrences()) - before
            assert created == int(case["expected_capture"]), case["input"]
            assert created <= 1
            if item is not None:
                assert item.accepted_answers == [evidence["correction"]]
                assert evidence["source_excerpt"] in item.prompt


def test_valid_model_candidate_wins_without_duplicate_fallback() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    request = _request("Yesterday I sleep early.")
    observation = LearningSignalObservation(
        error_type=LearningErrorType.VERB_TENSE,
        source_excerpt="sleep",
        correction="slept",
        confidence=LearningSignalConfidence.HIGH,
    )
    candidate = LearningSignalCandidate(
        source_conversation_id=request.conversation_id,
        source_user_message_id=request.user_message_id,
        source_assistant_message_id=request.assistant_message_id,
        kind=LearningKind.PHRASE,
        review_prompt='Complete: "Yesterday I ___ early."',
        accepted_answers=["slept"],
        reason=LearningSignalReason.CORRECTION,
    )

    with Session(engine) as session:
        repository = LearningRepository(session)
        item = LearningService(repository=repository).capture_conversation_signal(
            request=request, candidate=candidate, observation=observation
        )

        assert item is not None
        assert item.prompt == candidate.review_prompt
        assert len(repository.occurrences()) == 1
