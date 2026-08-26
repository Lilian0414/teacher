import math
from collections.abc import Sequence
from typing import Protocol

import httpx


class EmbeddingProvider(Protocol):
    """Async provider-neutral boundary for generating text embeddings."""

    async def embed(self, text: str) -> Sequence[float]:
        ...

    async def embed_many(self, texts: Sequence[str]) -> list[Sequence[float]]:
        ...

    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...


class OpenAIEmbeddingProvider:
    """Async OpenAI-compatible embedding client (including local servers)."""

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

    async def embed(self, text: str) -> Sequence[float]:
        return (await self.embed_many([text]))[0]

    async def embed_many(self, texts: Sequence[str]) -> list[Sequence[float]]:
        if not texts:
            return []
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        payload = {"input": list(texts), "model": self._model, "dimensions": self._dimensions}
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/embeddings", json=payload, headers=headers
            )
        response.raise_for_status()
        data = response.json()
        items = sorted(data["data"], key=lambda item: item.get("index", 0))
        if len(items) != len(texts):
            raise ValueError(f"Embedding model '{self._model}' returned an incomplete batch")
        vectors: list[Sequence[float]] = []
        for item in items:
            normalized = normalize_embedding(item["embedding"])
            if normalized is None or len(normalized) != self._dimensions:
                raise ValueError(
                    f"Embedding model '{self._model}' returned an incompatible dimension"
                )
            vectors.append(normalized)
        return vectors


def normalize_embedding(values: Sequence[float]) -> list[float] | None:
    """Return a finite, non-empty vector or ``None`` for unusable provider output."""

    try:
        normalized = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if not normalized or not all(math.isfinite(value) for value in normalized):
        return None
    return normalized
