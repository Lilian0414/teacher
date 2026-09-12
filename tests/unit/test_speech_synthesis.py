import httpx
import pytest

from companion.providers.errors import (
    LLMAuthenticationError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTemporaryError,
    LLMTimeoutError,
)
from companion.speech import ElevenLabsSpeechSynthesizer

HTTPX_ASYNC_CLIENT = httpx.AsyncClient


def synthesizer() -> ElevenLabsSpeechSynthesizer:
    return ElevenLabsSpeechSynthesizer(
        api_key="test-secret",
        voice_id="voice-id",
        model="eleven_v3",
        base_url="https://voice.invalid/v1/",
        output_format="pcm_24000",
        timeout_seconds=4,
    )


@pytest.mark.asyncio
async def test_elevenlabs_request_uses_header_and_configured_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen
        seen = request
        return httpx.Response(200, content=b"pcm")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: HTTPX_ASYNC_CLIENT(transport=transport, **kwargs),
    )

    assert await synthesizer().synthesize(" Hello ") == b"pcm"
    assert seen is not None
    assert seen.url == "https://voice.invalid/v1/text-to-speech/voice-id?output_format=pcm_24000"
    assert seen.headers["xi-api-key"] == "test-secret"
    assert seen.read() == b'{"text":"Hello","model_id":"eleven_v3"}'
    assert "test-secret" not in str(seen.url)


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, LLMAuthenticationError),
        (429, LLMRateLimitError),
        (500, LLMTemporaryError),
        (400, LLMInvalidResponseError),
    ],
)
@pytest.mark.asyncio
async def test_elevenlabs_maps_provider_statuses(
    monkeypatch: pytest.MonkeyPatch, status: int, error: type[Exception]
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, content=b"secret"))
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: HTTPX_ASYNC_CLIENT(transport=transport, **kwargs),
    )
    with pytest.raises(error, match="Speech|ElevenLabs") as raised:
        await synthesizer().synthesize("hello")
    assert "secret" not in str(raised.value)


@pytest.mark.asyncio
async def test_elevenlabs_maps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: HTTPX_ASYNC_CLIENT(transport=transport, **kwargs),
    )
    with pytest.raises(LLMTimeoutError):
        await synthesizer().synthesize("hello")


@pytest.mark.asyncio
async def test_elevenlabs_rejects_empty_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b""))
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: HTTPX_ASYNC_CLIENT(transport=transport, **kwargs),
    )
    with pytest.raises(LLMInvalidResponseError, match="empty audio"):
        await synthesizer().synthesize("hello")
