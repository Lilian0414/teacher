import json

import httpx
import pytest

from companion.providers.embeddings import OpenAIEmbeddingProvider


def test_openai_embedding_provider_sends_explicit_model_and_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request: httpx.Request | None = None

    def handler(value: httpx.Request) -> httpx.Response:
        nonlocal request
        request = value
        return httpx.Response(200, json={"data": [{"embedding": [0.25, 0.75]}]})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    provider = OpenAIEmbeddingProvider(
        base_url="http://local.test/v1",
        model="local-model",
        dimensions=2,
        timeout_seconds=1,
    )

    assert provider.embed("hello") == [0.25, 0.75]
    assert request is not None
    assert request.url == "http://local.test/v1/embeddings"
    assert json.loads(request.read()) == {
        "input": "hello",
        "model": "local-model",
        "dimensions": 2,
    }
