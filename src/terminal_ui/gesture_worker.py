"""Executable gesture helper with a small line-delimited JSON protocol."""

from __future__ import annotations

import json
import os
import select
import sys
from typing import Any

from terminal_ui.gestures import _gesture_worker


def _stop_requested() -> bool:
    readable, _, _ = select.select([sys.stdin], [], [], 0)
    if not readable:
        return False
    command = sys.stdin.readline()
    return not command or command.startswith("stop")


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit("expected pose model, gesture model, camera index, and log path")
    protocol_fd = os.dup(sys.stdout.fileno())
    protocol = os.fdopen(protocol_fd, "w", buffering=1)

    def send(message: tuple[Any, ...]) -> None:
        json.dump(message, protocol, separators=(",", ":"))
        protocol.write("\n")
        protocol.flush()

    _gesture_worker(send, _stop_requested, sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4])
    protocol.close()


if __name__ == "__main__":
    main()
