"""Bounded, local-only camera preview helpers."""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence

from rich.text import Text

type RGB = tuple[int, int, int]
type Frame = Sequence[Sequence[RGB]]


class LatestFrameBuffer:
    """A one-slot frame mailbox with explicit publication throttling."""

    def __init__(self, *, max_fps: float = 5.0) -> None:
        if max_fps <= 0:
            raise ValueError("max_fps must be positive")
        self._minimum_interval = 1.0 / max_fps
        self._latest: Frame | None = None
        self._last_published = float("-inf")
        self._lock = threading.Lock()

    def publish(self, frame: Frame, *, now: float | None = None) -> bool:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            if timestamp - self._last_published < self._minimum_interval:
                return False
            self._latest = frame
            self._last_published = timestamp
        return True

    def take_latest(self) -> Frame | None:
        with self._lock:
            frame, self._latest = self._latest, None
        return frame

    def clear(self) -> None:
        with self._lock:
            self._latest = None


def render_frame(frame: Frame, *, width: int = 48, height: int = 12) -> Text:
    """Render within a cell box while preserving the source pixel aspect ratio."""
    if width < 1 or height < 1 or not frame or not frame[0]:
        return Text("")
    source_height = len(frame)
    source_width = len(frame[0])
    output_width = min(width, max(1, round(height * 2 * source_width / source_height)))
    pixel_rows = min(height * 2, max(2, round(output_width * source_height / source_width)))
    pixel_rows -= pixel_rows % 2
    output = Text()
    for row in range(0, pixel_rows, 2):
        if row:
            output.append("\n")
        upper_y = min(source_height - 1, row * source_height // pixel_rows)
        lower_y = min(source_height - 1, (row + 1) * source_height // pixel_rows)
        for column in range(output_width):
            source_x = min(source_width - 1, column * source_width // output_width)
            upper = frame[upper_y][source_x]
            lower = frame[lower_y][source_x]
            output.append(
                "▀",
                style=(
                    f"rgb({upper[0]},{upper[1]},{upper[2]}) "
                    f"on rgb({lower[0]},{lower[1]},{lower[2]})"
                ),
            )
    return output
