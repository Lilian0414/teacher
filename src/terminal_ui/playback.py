import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol


class PlaybackBackend(Protocol):
    def play(
        self, audio: bytes, *, sample_rate: int, cancelled: threading.Event
    ) -> None: ...


class SoundDevicePlaybackBackend:
    """Play PCM while keeping every native stream operation on one worker."""

    _CHUNK_DURATION_SECONDS = 0.02
    _SAMPLE_WIDTH = 2

    def play(
        self, audio: bytes, *, sample_rate: int, cancelled: threading.Event
    ) -> None:
        if cancelled.is_set():
            return

        import sounddevice  # type: ignore[import-not-found]

        stream = sounddevice.RawOutputStream(
            samplerate=sample_rate, channels=1, dtype="int16"
        )
        try:
            if cancelled.is_set():
                return
            stream.start()
            chunk_size = max(
                self._SAMPLE_WIDTH,
                int(sample_rate * self._CHUNK_DURATION_SECONDS) * self._SAMPLE_WIDTH,
            )
            for offset in range(0, len(audio), chunk_size):
                if cancelled.is_set():
                    break
                stream.write(audio[offset : offset + chunk_size])
            stream.stop()
        finally:
            stream.close()


class AudioPlayer:
    """Play one in-memory utterance at a time without blocking the event loop."""

    def __init__(self, backend: PlaybackBackend | None = None) -> None:
        self._backend = backend or SoundDevicePlaybackBackend()
        self._task: asyncio.Task[None] | None = None
        self._cancellation: threading.Event | None = None
        self._closed = False
        # One worker ensures a cancelled utterance exits before its replacement starts.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio-playback")

    def play(self, audio: bytes, *, sample_rate: int) -> None:
        if self._closed:
            return
        self.stop()
        cancellation = threading.Event()
        self._cancellation = cancellation
        self._task = asyncio.create_task(
            self._play(audio, sample_rate=sample_rate, cancelled=cancellation)
        )

    async def _play(
        self, audio: bytes, *, sample_rate: int, cancelled: threading.Event
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                self._executor,
                lambda: self._backend.play(
                    audio, sample_rate=sample_rate, cancelled=cancelled
                ),
            )
        except (Exception, asyncio.CancelledError):
            return

    def stop(self) -> None:
        if self._cancellation is not None:
            self._cancellation.set()
            self._cancellation = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def close(self) -> None:
        """Signal cancellation, wait for native cleanup, and release the worker."""
        if self._closed:
            return
        self._closed = True
        self.stop()
        self._executor.shutdown(wait=True, cancel_futures=True)
