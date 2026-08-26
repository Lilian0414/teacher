import re
from collections.abc import Sequence

from companion.learning.normalization import normalize_learning_text

# Only contractions with one context-independent expansion belong here. Ambiguous
# forms such as "he's" ("he is" or "he has") intentionally remain unsupported.
_SAFE_CONTRACTIONS = {
    "i'm": "i am",
    "you're": "you are",
    "we're": "we are",
    "they're": "they are",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "can't": "cannot",
    "couldn't": "could not",
    "won't": "will not",
    "wouldn't": "would not",
    "shouldn't": "should not",
}
_SAFE_CONTRACTION_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(value) for value in _SAFE_CONTRACTIONS) + r")\b"
)


class AnswerGradingPolicy:
    """Grade only exact answers and a bounded set of deterministic variants."""

    def grade(self, submitted_answer: str, accepted_answers: Sequence[str]) -> bool:
        submitted = normalize_learning_text(submitted_answer)
        if not submitted:
            return False

        accepted = [normalize_learning_text(answer) for answer in accepted_answers]
        if submitted in accepted:
            return True

        canonical_submitted = self._canonicalize(submitted)
        return any(
            canonical_submitted == self._canonicalize(candidate)
            for candidate in accepted
            if candidate
        )

    @staticmethod
    def _canonicalize(value: str) -> str:
        return _SAFE_CONTRACTION_PATTERN.sub(
            lambda match: _SAFE_CONTRACTIONS[match.group(0)], value
        )
