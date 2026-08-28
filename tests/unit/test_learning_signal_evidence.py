import json
from pathlib import Path
from typing import Any

import pytest

from companion.learning.schemas import (
    LearningErrorType,
    LearningSignalConfidence,
    LearningSignalObservation,
    LearningSignalRequest,
)
from companion.learning.service import LearningService


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


def test_offline_eval_fixture_covers_required_precision_and_recall_cases() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "learning_signal_eval.json"
    cases: list[dict[str, Any]] = json.loads(fixture.read_text())

    captures = [case for case in cases if case["expected_capture"]]
    controls = [case for case in cases if not case["expected_capture"]]
    assert {case["required_token"] for case in captures} >= {"slept", "missed", "receive"}
    assert {case["expected_error_type"] for case in captures} >= {"spelling", "verb_tense"}
    assert len(controls) >= 7
    assert any(case.get("max_candidates") == 1 for case in captures)
