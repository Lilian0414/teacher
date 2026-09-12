import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol


class PlaybackBackend(Protocol):
    def play(self, audio: bytes, *, sample_rate: int) -> None: ...

    def stop(self) -> None: ...


class SoundDevicePlaybackBackend:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream: object | None = None

    def play(self, audio: bytes, *, sample_rate: int) -> None:
        import sounddevice  # type: ignore[import-not-found]

        stream = sounddevice.RawOutputStream(
            samplerate=sample_rate, channels=1, dtype="int16"
        )
        with self._lock:
            self._stream = stream
        try:
            stream.start()
            stream.write(audio)
        finally:
            with self._lock:
                if self._stream is stream:
                    self._stream = None
            stream.close()

    def stop(self) -> None:
        with self._lock:
            stream = self._stream
        if stream is not None:
            stream.abort()  # type: ignore[attr-defined]
            stream.close()  # type: ignore[attr-defined]


class AudioPlayer:
    """Play one in-memory utterance at a time without blocking the event loop."""

    def __init__(self, backend: PlaybackBackend | None = None) -> None:
        self._backend = backend or SoundDevicePlaybackBackend()
        self._task: asyncio.Task[None] | None = None
        # A single worker preserves replacement order even though cancelling an
        # asyncio Future cannot terminate a thread already inside stream.write().
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio-playback")

    def play(self, audio: bytes, *, sample_rate: int) -> None:
        self.stop()
        self._task = asyncio.create_task(self._play(audio, sample_rate=sample_rate))

    async def _play(self, audio: bytes, *, sample_rate: int) -> None:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                self._executor, lambda: self._backend.play(audio, sample_rate=sample_rate)
            )
        except (Exception, asyncio.CancelledError):
            return

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        try:
            self._backend.stop()
        except Exception:
            pass
