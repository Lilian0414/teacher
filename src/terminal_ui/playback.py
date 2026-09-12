import asyncio
from typing import Protocol


class PlaybackBackend(Protocol):
    def play(self, audio: bytes, *, sample_rate: int) -> None: ...

    def stop(self) -> None: ...


class SoundDevicePlaybackBackend:
    def play(self, audio: bytes, *, sample_rate: int) -> None:
        import sounddevice  # type: ignore[import-not-found]

        with sounddevice.RawOutputStream(
            samplerate=sample_rate, channels=1, dtype="int16"
        ) as stream:
            stream.write(audio)

    def stop(self) -> None:
        import sounddevice

        sounddevice.stop()


class AudioPlayer:
    """Play one in-memory utterance at a time without blocking the event loop."""

    def __init__(self, backend: PlaybackBackend | None = None) -> None:
        self._backend = backend or SoundDevicePlaybackBackend()
        self._task: asyncio.Task[None] | None = None

    def play(self, audio: bytes, *, sample_rate: int) -> None:
        self.stop()
        self._task = asyncio.create_task(self._play(audio, sample_rate=sample_rate))

    async def _play(self, audio: bytes, *, sample_rate: int) -> None:
        try:
            await asyncio.to_thread(self._backend.play, audio, sample_rate=sample_rate)
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
