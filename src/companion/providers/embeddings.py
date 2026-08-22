import math
from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Provider-neutral boundary for generating one text embedding."""

    def embed(self, text: str) -> Sequence[float]:
        ...


def normalize_embedding(values: Sequence[float]) -> list[float] | None:
    """Return a finite, non-empty vector or ``None`` for unusable provider output."""

    try:
        normalized = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if not normalized or not all(math.isfinite(value) for value in normalized):
        return None
    return normalized
