import asyncio
import io
import threading
import wave
from enum import StrEnum
from typing import Any


class MicrophoneUnavailableError(RuntimeError):
    pass


class RecorderState(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


class MacMicrophoneRecorder:
    """Capture one explicitly bounded WAV in memory; never write audio to disk."""

    def __init__(self, *, sample_rate: int = 16_000) -> None:
        self._sample_rate = sample_rate
        self._state = RecorderState.IDLE
        self._frames = bytearray()
        self._stream: Any | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> RecorderState:
        return self._state

    async def start(self) -> None:
        await asyncio.to_thread(self._start_sync)

    def _start_sync(self) -> None:
        with self._lock:
            if self._state == RecorderState.RECORDING:
                raise RuntimeError("Recording is already active")
            self._frames.clear()
            self._state = RecorderState.RECORDING
        try:
            import sounddevice  # type: ignore[import-not-found]

            stream = sounddevice.RawInputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                callback=self._capture,
            )
            stream.start()
        except (ImportError, OSError, RuntimeError) as exc:
            with self._lock:
                self._state = RecorderState.IDLE
            raise MicrophoneUnavailableError(
                "Microphone unavailable. Check macOS microphone permission and PortAudio setup."
            ) from exc
        with self._lock:
            self._stream = stream

    def _capture(self, data: bytes, _frames: int, _time: object, _status: object) -> None:
        with self._lock:
            if self._state == RecorderState.RECORDING:
                self._frames.extend(data)

    async def stop(self) -> bytes:
        return await asyncio.to_thread(self._finish_sync, False)

    async def cancel(self) -> None:
        await asyncio.to_thread(self._finish_sync, True)

    def _finish_sync(self, cancelled: bool) -> bytes:
        with self._lock:
            if self._state != RecorderState.RECORDING:
                return b""
            stream = self._stream
            self._stream = None
            self._state = RecorderState.CANCELLED if cancelled else RecorderState.STOPPED
        if stream is not None:
            stream.stop()
            stream.close()
        if cancelled:
            with self._lock:
                self._frames.clear()
            return b""
        with self._lock:
            frames = bytes(self._frames)
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self._sample_rate)
            wav.writeframes(frames)
        return output.getvalue()
