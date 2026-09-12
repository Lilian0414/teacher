from typing import Protocol

import httpx

from companion.providers.errors import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMInvalidResponseError,
    LLMRateLimitError,
    LLMTemporaryError,
    LLMTimeoutError,
)


class SpeechTranscriber(Protocol):
    async def transcribe(self, audio: bytes, *, content_type: str) -> str: ...


class SpeechSynthesizer(Protocol):
    async def synthesize(self, text: str) -> bytes: ...


def pcm_sample_rate(output_format: str) -> int:
    """Return the sample rate encoded by a raw 16-bit PCM output format."""
    prefix = "pcm_"
    value = output_format.removeprefix(prefix)
    if not output_format.startswith(prefix) or not value.isascii() or not value.isdigit():
        raise ValueError("ELEVENLABS_OUTPUT_FORMAT must be pcm_<sample_rate>")
    sample_rate = int(value)
    if sample_rate <= 0:
        raise ValueError("ELEVENLABS_OUTPUT_FORMAT sample rate must be positive")
    return sample_rate


class ElevenLabsSpeechSynthesizer:
    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str,
        model: str,
        base_url: str,
        output_format: str,
        timeout_seconds: float,
    ) -> None:
        pcm_sample_rate(output_format)
        self._api_key = api_key
        self._voice_id = voice_id
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._output_format = output_format
        self._timeout_seconds = timeout_seconds

    async def synthesize(self, text: str) -> bytes:
        if not self._api_key:
            raise LLMConfigurationError("ELEVENLABS_API_KEY is not configured")
        if not text.strip():
            raise LLMInvalidResponseError("Speech synthesis text is empty")
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/text-to-speech/{self._voice_id}",
                    params={"output_format": self._output_format},
                    headers={"xi-api-key": self._api_key},
                    json={"text": text.strip(), "model_id": self._model},
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Speech synthesis timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMTemporaryError("Speech synthesis failed temporarily") from exc
        if response.status_code in {401, 403}:
            raise LLMAuthenticationError("Speech synthesis authentication failed")
        if response.status_code == 429:
            raise LLMRateLimitError("Speech synthesis rate limit reached")
        if response.status_code >= 500:
            raise LLMTemporaryError("Speech synthesis is temporarily unavailable")
        if response.status_code >= 400:
            raise LLMInvalidResponseError("ElevenLabs rejected the speech synthesis request")
        if not response.content:
            raise LLMInvalidResponseError("Speech synthesis returned empty audio")
        return response.content


class GroqSpeechTranscriber:
    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: float) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def transcribe(self, audio: bytes, *, content_type: str) -> str:
        if not self._api_key:
            raise LLMConfigurationError("GROQ_API_KEY is not configured")
        if not audio:
            raise LLMInvalidResponseError("Audio is empty")
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    data={"model": self._model, "response_format": "json"},
                    files={"file": ("review.wav", audio, content_type)},
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Speech transcription timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMTemporaryError("Speech transcription failed temporarily") from exc
        if response.status_code in {401, 403}:
            raise LLMAuthenticationError("Speech transcription authentication failed")
        if response.status_code == 429:
            raise LLMRateLimitError("Speech transcription rate limit reached")
        if response.status_code >= 500:
            raise LLMTemporaryError("Speech transcription is temporarily unavailable")
        if response.status_code >= 400:
            raise LLMInvalidResponseError("Groq rejected the audio transcription request")
        try:
            transcript = response.json()["text"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMInvalidResponseError(
                "Speech transcription returned an invalid response"
            ) from exc
        if not isinstance(transcript, str) or not transcript.strip():
            raise LLMInvalidResponseError("Speech transcription was empty")
        return transcript.strip()
