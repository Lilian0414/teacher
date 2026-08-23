import math
from collections.abc import Sequence
from typing import Protocol

import httpx


class EmbeddingProvider(Protocol):
    """Provider-neutral boundary for generating one text embedding."""

    def embed(self, text: str) -> Sequence[float]:
        ...

    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...


class OpenAIEmbeddingProvider:
    """Synchronous OpenAI-compatible embedding client (including local servers)."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimensions: int,
        timeout_seconds: float,
        api_key: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> Sequence[float]:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        payload = {"input": text, "model": self._model, "dimensions": self._dimensions}
        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(f"{self._base_url}/embeddings", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        vector = data["data"][0]["embedding"]
        normalized = normalize_embedding(vector)
        if normalized is None or len(normalized) != self._dimensions:
            raise ValueError(
                f"Embedding model '{self._model}' returned an incompatible dimension"
            )
        return normalized


def normalize_embedding(values: Sequence[float]) -> list[float] | None:
    """Return a finite, non-empty vector or ``None`` for unusable provider output."""

    try:
        normalized = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if not normalized or not all(math.isfinite(value) for value in normalized):
        return None
    return normalized
