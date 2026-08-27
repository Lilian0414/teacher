import re
from dataclasses import dataclass

from companion.learning.normalization import normalize_learning_text

_UNRESOLVED_CONTEXT_REFERENCE = re.compile(
    r"\b(?:"
    r"the user(?:'s|’s) (?:sentence|phrase|word)"
    r"|the (?:sentence|phrase|word) above"
    r"|the previous (?:sentence|phrase|word)"
    r"|(?:this|that) (?:sentence|phrase|word)"
    r")\b",
    re.IGNORECASE,
)
_QUOTED_SOURCE = re.compile(r'(?:["“][^"”]{2,}["”]|[\'‘][^\'’]{2,}[\'’])')
_MAX_ANSWER_CHARACTERS = 200
_MAX_ANSWER_WORDS = 30


@dataclass(frozen=True)
class ValidatedLearningSignal:
    prompt: str
    accepted_answers: list[str]


def validate_learning_signal(
    *, prompt: str, accepted_answers: list[str]
) -> ValidatedLearningSignal | None:
    """Validate and normalize the provider-controlled parts of a learning signal."""
    clean_prompt = prompt.strip()
    if not _is_reviewable(clean_prompt):
        return None
    if _UNRESOLVED_CONTEXT_REFERENCE.search(clean_prompt) and not _QUOTED_SOURCE.search(
        clean_prompt
    ):
        return None

    clean_answers: list[str] = []
    seen: set[str] = set()
    for answer in accepted_answers:
        clean_answer = answer.strip()
        if not clean_answer:
            continue
        normalized = normalize_learning_text(clean_answer)
        if (
            not _is_reviewable(clean_answer)
            or len(clean_answer) > _MAX_ANSWER_CHARACTERS
            or len(clean_answer.split()) > _MAX_ANSWER_WORDS
        ):
            return None
        if normalized not in seen:
            seen.add(normalized)
            clean_answers.append(clean_answer)

    if not clean_answers:
        return None
    return ValidatedLearningSignal(prompt=clean_prompt, accepted_answers=clean_answers)


def _is_reviewable(value: str) -> bool:
    normalized = normalize_learning_text(value)
    return len(normalized) >= 3 and normalized not in {"hello", "hi", "hey", "thanks"}
