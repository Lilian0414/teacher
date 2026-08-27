import asyncio
import io
import threading
import wave


class MicrophoneUnavailableError(RuntimeError):
    pass


class MacMicrophoneRecorder:
    """Capture a short WAV in memory; no recording is written to disk."""

    def __init__(self, *, seconds: float = 5, sample_rate: int = 16_000) -> None:
        self._seconds = seconds
        self._sample_rate = sample_rate
        self._cancelled = threading.Event()

    async def record(self) -> bytes:
        self._cancelled.clear()
        return await asyncio.to_thread(self._record_sync)

    def cancel(self) -> None:
        """Request that an in-progress capture stop without producing an answer."""
        self._cancelled.set()

    def _record_sync(self) -> bytes:
        try:
            import sounddevice  # type: ignore[import-not-found]

            frames = bytearray()
            block_frames = max(1, self._sample_rate // 10)
            remaining = int(self._seconds * self._sample_rate)
            with sounddevice.RawInputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
            ) as stream:
                while remaining > 0 and not self._cancelled.is_set():
                    chunk, _overflowed = stream.read(min(block_frames, remaining))
                    frames.extend(chunk)
                    remaining -= len(chunk) // 2
        except (ImportError, OSError, RuntimeError) as exc:
            raise MicrophoneUnavailableError(
                "Microphone unavailable. Check macOS microphone permission and PortAudio setup."
            ) from exc
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self._sample_rate)
            wav.writeframes(frames)
        return output.getvalue()
