import pytest

from companion.learning.prompts import LEARNING_SIGNAL_SYSTEM_PROMPT
from companion.learning.signal_policy import validate_learning_signal


@pytest.mark.parametrize(
    ("prompt", "answer"),
    [
        ('What is the correct spelling of "perents"?', "parents"),
        ('What is the correct past tense of "go"?', "went"),
        ('Correct this sentence: "I goed home."', "I went home."),
    ],
)
def test_signal_policy_accepts_standalone_learning_items(prompt: str, answer: str) -> None:
    validated = validate_learning_signal(prompt=prompt, accepted_answers=[answer])

    assert validated is not None
    assert validated.prompt == prompt
    assert validated.accepted_answers == [answer]


@pytest.mark.parametrize(
    "prompt",
    [
        "Correct the misspelled word in the user's sentence.",
        "Correct the sentence above.",
        "What does the phrase above mean?",
        "Fix this sentence.",
        "What is wrong with that phrase?",
        "Correct the previous sentence.",
    ],
)
def test_signal_policy_rejects_unresolved_context_references(prompt: str) -> None:
    assert validate_learning_signal(prompt=prompt, accepted_answers=["answer"]) is None


def test_signal_policy_normalizes_and_deduplicates_answers_without_rewriting() -> None:
    validated = validate_learning_signal(
        prompt='What is the correct spelling of "perents"?',
        accepted_answers=[" parents ", "", "PARENTS!", "parents"],
    )

    assert validated is not None
    assert validated.accepted_answers == ["parents"]


@pytest.mark.parametrize("answer", ["", "  ", "word " * 31, "x" * 201])
def test_signal_policy_rejects_empty_or_clearly_verbose_answers(answer: str) -> None:
    assert (
        validate_learning_signal(
            prompt='What is the correct spelling of "perents"?', accepted_answers=[answer]
        )
        is None
    )


def test_learning_signal_prompt_states_standalone_generation_contract() -> None:
    prompt = LEARNING_SIGNAL_SYSTEM_PROMPT

    assert "`candidate=null` is\nbetter" in prompt
    assert "standalone, future-facing" in prompt
    assert "no transcript" in prompt
    assert "actual misspelling or token" in prompt
    assert "one to three answers" in prompt
    assert "Copy all source IDs exactly" in prompt
    assert "scheduling metadata" in prompt
