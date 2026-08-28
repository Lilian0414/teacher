from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from companion.learning import LearningRepository, LearningService
from companion.persistence.database import Base, make_engine
from companion.providers.errors import (
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from companion.providers.schemas import (
    LanguageHelpMode,
    LanguageHelpResponse,
    SemanticGradeDecision,
    SemanticGradeRequest,
    SemanticGradeVerdict,
)


class SemanticJudge:
    def __init__(self, decision: SemanticGradeDecision) -> None:
        self.decision = decision
        self.requests: list[SemanticGradeRequest] = []
        self.error: Exception | None = None

    async def grade_review_answer(self, request: SemanticGradeRequest) -> SemanticGradeDecision:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.decision

    # The semantic grading service consumes only the narrow method above. These declarations
    # deliberately make this fixture structurally compatible without exercising other tasks.
    chat = provide_language_help = analyze_memory = extract_memory_candidates = None
    extract_learning_signal = None


def make_review(
    *, prompt: str, accepted: str
) -> tuple[LearningRepository, LearningService, str, datetime]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime(2026, 8, 28, 12, tzinfo=UTC)
    repository = LearningRepository(session)
    service = LearningService(repository=repository, clock=lambda: now)
    item = service.capture_assistance(
        mode=LanguageHelpMode.HELP,
        prompt=prompt,
        response=LanguageHelpResponse(natural_expression=accepted),
    )
    assert item is not None
    return repository, service, item.id, now


def decision(verdict: SemanticGradeVerdict, target_preserved: bool | None) -> SemanticGradeDecision:
    return SemanticGradeDecision(
        verdict=verdict,
        target_preserved=target_preserved,
        reason="Bounded learner-safe grading reason.",
    )


@pytest.mark.parametrize("submitted", ["I am tired.", "I'm tired.", "  I AM TIRED! "])
async def test_deterministic_variants_skip_semantic_judge(submitted: str) -> None:
    repository, service, item_id, _ = make_review(
        prompt="Say that you are tired.", accepted="I am tired."
    )
    judge = SemanticJudge(decision(SemanticGradeVerdict.CORRECT, True))

    result = await service.answer(item_id=item_id, answer=submitted, llm_provider=judge)  # type: ignore[arg-type]

    assert result.correct is True
    assert judge.requests == []
    assert len(repository.attempts_for(item_id)) == 1


@pytest.mark.parametrize(
    ("prompt", "accepted", "submitted", "verdict"),
    [
        (
            "Express the same meaning: I went to bed early yesterday.",
            "I went to bed early yesterday.",
            "I went to sleep early yesterday.",
            SemanticGradeVerdict.CORRECT,
        ),
        (
            "Use the past tense to say you went to bed early yesterday.",
            "I went to bed early yesterday.",
            "I go to bed early.",
            SemanticGradeVerdict.INCORRECT,
        ),
        (
            "Say that you are not tired.",
            "I am not tired.",
            "I am tired.",
            SemanticGradeVerdict.INCORRECT,
        ),
        (
            "Use the phrase 'worn out'.",
            "I am worn out.",
            "I am tired.",
            SemanticGradeVerdict.INCORRECT,
        ),
        (
            "Say that you went to bed early.",
            "I went to bed early.",
            "Nice weather.",
            SemanticGradeVerdict.INCORRECT,
        ),
    ],
)
async def test_goal_aware_fallback_resolves_once(
    prompt: str, accepted: str, submitted: str, verdict: SemanticGradeVerdict
) -> None:
    repository, service, item_id, _ = make_review(prompt=prompt, accepted=accepted)
    judge = SemanticJudge(decision(verdict, verdict == SemanticGradeVerdict.CORRECT))

    result = await service.answer(item_id=item_id, answer=submitted, llm_provider=judge)  # type: ignore[arg-type]

    assert result.correct is (verdict == SemanticGradeVerdict.CORRECT)
    assert len(judge.requests) == 1
    request = judge.requests[0]
    assert request.review_prompt == prompt
    assert request.kind == "expression"
    assert request.accepted_answers == [accepted]
    assert request.submitted_answer == submitted
    assert len(repository.attempts_for(item_id)) == 1


@pytest.mark.parametrize(
    "provider_error",
    [
        None,
        LLMTimeoutError("timeout"),
        LLMRateLimitError("limited"),
        LLMInvalidResponseError("invalid"),
    ],
)
async def test_uncertain_or_provider_failure_never_mutates(
    provider_error: Exception | None,
) -> None:
    repository, service, item_id, now = make_review(
        prompt="Use the target expression.", accepted="I am worn out."
    )
    judge = SemanticJudge(decision(SemanticGradeVerdict.UNCERTAIN, None))
    judge.error = provider_error

    result = await service.answer(item_id=item_id, answer="I am tired.", llm_provider=judge)  # type: ignore[arg-type]

    stored = repository.get_item(item_id, user_id="default")
    assert result.correct is None
    assert result.grading_deferred is True
    assert result.feedback == "I couldn't grade that confidently — try another wording."
    assert stored is not None and stored.stage == 0 and stored.next_review_at == now.isoformat()
    assert repository.attempts_for(item_id) == []


async def test_same_transcript_has_same_result_for_typed_and_spoken_canonical_path() -> None:
    results: list[bool | None] = []
    for _modality in ("typed", "spoken"):
        _, service, item_id, _ = make_review(
            prompt="Express the same meaning.", accepted="I went to bed early yesterday."
        )
        judge = SemanticJudge(decision(SemanticGradeVerdict.CORRECT, True))
        result = await service.answer(
            item_id=item_id,
            answer="I went to sleep early yesterday.",
            llm_provider=judge,  # type: ignore[arg-type]
        )
        results.append(result.correct)

    assert results == [True, True]
