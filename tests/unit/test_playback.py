import asyncio

import pytest

from terminal_ui.playback import AudioPlayer


class FakeBackend:
    def __init__(self) -> None:
        self.started: list[tuple[bytes, int]] = []
        self.stops = 0

    def play(self, audio: bytes, *, sample_rate: int) -> None:
        self.started.append((audio, sample_rate))

    def stop(self) -> None:
        self.stops += 1


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
