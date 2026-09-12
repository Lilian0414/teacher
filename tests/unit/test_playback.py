import asyncio
import sys
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from terminal_ui.playback import AudioPlayer, SoundDevicePlaybackBackend


class FakeBackend:
    def __init__(self) -> None:
        self.started: list[tuple[bytes, int]] = []
        self.stops = 0

    def play(self, audio: bytes, *, sample_rate: int) -> None:
        self.started.append((audio, sample_rate))

    def stop(self) -> None:
        self.stops += 1


class BlockingBackend:
    def __init__(self) -> None:
        self.started: list[bytes] = []
        self.first_started = threading.Event()
        self.first_stopped = threading.Event()
        self.overlapped = False

    def play(self, audio: bytes, *, sample_rate: int) -> None:
        if audio == b"second" and not self.first_stopped.is_set():
            self.overlapped = True
        self.started.append(audio)
        if audio == b"first":
            self.first_started.set()
            self.first_stopped.wait(timeout=1)

    def stop(self) -> None:
        if self.first_started.is_set():
            self.first_stopped.set()


@pytest.mark.asyncio
async def test_new_playback_stops_previous_utterance() -> None:
    backend = FakeBackend()
    player = AudioPlayer(backend)
    player.play(b"first", sample_rate=24000)
    await asyncio.sleep(0)
    player.play(b"second", sample_rate=24000)
    await asyncio.sleep(0.05)

    assert backend.stops >= 2
    assert backend.started[-1] == (b"second", 24000)
    player.stop()


@pytest.mark.asyncio
async def test_replacement_waits_until_interrupted_playback_has_exited() -> None:
    backend = BlockingBackend()
    player = AudioPlayer(backend)
    player.play(b"first", sample_rate=24000)
    assert await asyncio.to_thread(backend.first_started.wait, 1)

    player.play(b"second", sample_rate=24000)
    await asyncio.sleep(0.05)

    assert backend.first_stopped.is_set()
    assert backend.started == [b"first", b"second"]
    assert backend.overlapped is False
    player.stop()


@pytest.mark.asyncio
async def test_stop_during_stream_creation_prevents_stale_playback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    creating_first = threading.Event()
    allow_first_creation = threading.Event()
    streams: list[Any] = []

    class FakeStream:
        def __init__(self, *, samplerate: int, channels: int, dtype: str) -> None:
            self.started = False
            self.writes: list[bytes] = []
            self.closed = False
            streams.append(self)
            if len(streams) == 1:
                creating_first.set()
                allow_first_creation.wait(timeout=1)

        def start(self) -> None:
            self.started = True

        def write(self, audio: bytes) -> None:
            self.writes.append(audio)

        def abort(self) -> None:
            pass

        def close(self) -> None:
            self.closed = True

    monkeypatch.setitem(
        sys.modules, "sounddevice", SimpleNamespace(RawOutputStream=FakeStream)
    )
    player = AudioPlayer(SoundDevicePlaybackBackend())
    player.play(b"first", sample_rate=24000)
    assert await asyncio.to_thread(creating_first.wait, 1)

    player.play(b"second", sample_rate=24000)
    allow_first_creation.set()
    await asyncio.sleep(0.05)

    assert streams[0].started is False
    assert streams[0].writes == []
    assert streams[0].closed is True
    assert streams[1].started is True
    assert streams[1].writes == [b"second"]
    player.close()


@pytest.mark.asyncio
async def test_close_stops_playback_and_prevents_future_jobs() -> None:
    backend = FakeBackend()
    player = AudioPlayer(backend)
    player.play(b"first", sample_rate=24000)
    await asyncio.sleep(0.05)

    player.close()
    stops_after_close = backend.stops
    player.play(b"second", sample_rate=24000)
    await asyncio.sleep(0)

    assert backend.stops == stops_after_close
    assert backend.started == [(b"first", 24000)]
