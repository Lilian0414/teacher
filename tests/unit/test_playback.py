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
        self.cancelled: list[threading.Event] = []

    def play(
        self, audio: bytes, *, sample_rate: int, cancelled: threading.Event
    ) -> None:
        self.started.append((audio, sample_rate))
        self.cancelled.append(cancelled)


class BlockingBackend:
    def __init__(self) -> None:
        self.started: list[bytes] = []
        self.first_started = threading.Event()
        self.first_exited = threading.Event()
        self.overlapped = False

    def play(
        self, audio: bytes, *, sample_rate: int, cancelled: threading.Event
    ) -> None:
        if audio == b"second" and not self.first_exited.is_set():
            self.overlapped = True
        self.started.append(audio)
        if audio == b"first":
            self.first_started.set()
            cancelled.wait(timeout=1)
            self.first_exited.set()


@pytest.mark.asyncio
async def test_replacement_signals_active_job_without_native_caller_work() -> None:
    backend = BlockingBackend()
    player = AudioPlayer(backend)
    player.play(b"first", sample_rate=24000)
    assert await asyncio.to_thread(backend.first_started.wait, 1)

    player.play(b"second", sample_rate=24000)
    await asyncio.sleep(0.05)

    assert backend.first_exited.is_set()
    assert backend.started == [b"first", b"second"]
    assert backend.overlapped is False
    player.close()


@pytest.mark.asyncio
async def test_stream_lifecycle_is_worker_owned_and_pcm_is_chunked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller_thread = threading.get_ident()
    first_write = threading.Event()
    allow_write_to_finish = threading.Event()
    streams: list[Any] = []

    class FakeStream:
        def __init__(self, *, samplerate: int, channels: int, dtype: str) -> None:
            self.calls: list[tuple[str, int]] = []
            self.writes: list[bytes] = []
            streams.append(self)

        def start(self) -> None:
            self.calls.append(("start", threading.get_ident()))

        def write(self, audio: bytes) -> None:
            self.calls.append(("write", threading.get_ident()))
            self.writes.append(audio)
            if len(streams) == 1:
                first_write.set()
                allow_write_to_finish.wait(timeout=1)

        def stop(self) -> None:
            self.calls.append(("stop", threading.get_ident()))

        def close(self) -> None:
            self.calls.append(("close", threading.get_ident()))

    monkeypatch.setitem(
        sys.modules, "sounddevice", SimpleNamespace(RawOutputStream=FakeStream)
    )
    player = AudioPlayer(SoundDevicePlaybackBackend())
    player.play(b"a" * 4000, sample_rate=24000)
    assert await asyncio.to_thread(first_write.wait, 1)

    player.play(b"second", sample_rate=24000)
    # The caller only signals cancellation; it performs no native stream operation.
    assert [name for name, _ in streams[0].calls] == ["start", "write"]
    allow_write_to_finish.set()
    await asyncio.sleep(0.05)
    player.close()

    assert len(streams[0].writes) == 1
    assert streams[1].writes == [b"second"]
    assert all(
        thread_id != caller_thread
        for stream in streams
        for _, thread_id in stream.calls
    )
    assert all(
        len({thread_id for _, thread_id in stream.calls}) == 1 for stream in streams
    )
    assert [[name for name, _ in stream.calls] for stream in streams] == [
        ["start", "write", "stop", "close"],
        ["start", "write", "stop", "close"],
    ]


@pytest.mark.asyncio
async def test_cancelled_queued_job_exits_before_replacement_starts() -> None:
    backend = BlockingBackend()
    player = AudioPlayer(backend)
    player.play(b"first", sample_rate=24000)
    assert await asyncio.to_thread(backend.first_started.wait, 1)

    player.play(b"stale", sample_rate=24000)
    player.play(b"second", sample_rate=24000)
    await asyncio.sleep(0.05)

    assert backend.first_exited.is_set()
    assert backend.started == [b"first", b"second"]
    assert backend.overlapped is False
    player.close()


@pytest.mark.asyncio
async def test_close_waits_for_worker_cleanup_and_prevents_future_jobs() -> None:
    backend = BlockingBackend()
    player = AudioPlayer(backend)
    player.play(b"first", sample_rate=24000)
    assert await asyncio.to_thread(backend.first_started.wait, 1)

    player.close()
    assert backend.first_exited.is_set()
    player.play(b"second", sample_rate=24000)
    await asyncio.sleep(0)

    assert backend.started == [b"first"]
