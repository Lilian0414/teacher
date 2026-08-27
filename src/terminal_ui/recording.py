import asyncio
import io
import wave
from typing import Any


class MicrophoneUnavailableError(RuntimeError):
    pass


class MacMicrophoneRecorder:
    """Capture a short WAV in memory; no recording is written to disk."""

    def __init__(self, *, seconds: float = 5, sample_rate: int = 16_000) -> None:
        self._seconds = seconds
        self._sample_rate = sample_rate

    async def record(self) -> bytes:
        return await asyncio.to_thread(self._record_sync)

    def _record_sync(self) -> bytes:
        try:
            import sounddevice  # type: ignore[import-not-found]

            frames: Any = sounddevice.rec(
                int(self._seconds * self._sample_rate),
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
            )
            sounddevice.wait()
        except (ImportError, OSError, RuntimeError) as exc:
            raise MicrophoneUnavailableError(
                "Microphone unavailable. Check macOS microphone permission and PortAudio setup."
            ) from exc
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self._sample_rate)
            wav.writeframes(frames.tobytes())
        return output.getvalue()
