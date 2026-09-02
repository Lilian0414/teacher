"""Local gesture recognition isolated from Textual in a child process."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from companion.settings import get_settings
from terminal_ui.preview import Frame


class GestureIntent(StrEnum):
    UNCERTAINTY = "uncertainty"
    THUMBS_UP = "thumbs_up"


class GestureFailure(StrEnum):
    MODEL_NOT_CONFIGURED = "model_not_configured"
    MODEL_ASSET_MISSING = "model_asset_missing"
    DEPENDENCY_MISSING = "dependency_missing"
    CAMERA_UNAVAILABLE = "camera_unavailable"
    RUNTIME_FAILED = "runtime_failed"


_MESSAGES = {
    GestureFailure.MODEL_NOT_CONFIGURED: "Gesture models are not configured",
    GestureFailure.MODEL_ASSET_MISSING: "Gesture model files are missing",
    GestureFailure.DEPENDENCY_MISSING: "Gesture support is not installed",
    GestureFailure.CAMERA_UNAVAILABLE: "Camera unavailable or permission denied",
    GestureFailure.RUNTIME_FAILED: "Gesture runtime unavailable",
}

PREVIEW_TARGET_FPS = 12.0
# Compatibility name consumed by the current Textual UI.
PREVIEW_FPS = PREVIEW_TARGET_FPS
PREVIEW_INTERVAL_SECONDS = 1.0 / PREVIEW_TARGET_FPS
PREVIEW_PAYLOAD_WIDTH = 192
INFERENCE_INTERVAL_SECONDS = 0.1


class GestureUnavailableError(RuntimeError):
    def __init__(self, message: str, *, failure: GestureFailure = GestureFailure.RUNTIME_FAILED):
        super().__init__(message)
        self.failure = failure

    @property
    def learner_message(self) -> str:
        return _MESSAGES[self.failure]


class GestureAdapter(Protocol):
    def start(self, callback: Callable[[GestureIntent], None]) -> None: ...
    def stop(self) -> None: ...


def classify_gesture(
    categories: Sequence[tuple[str, float]], *, threshold: float = 0.7
) -> GestureIntent | None:
    for name, score in categories:
        if score < threshold:
            continue
        if name == "Thumb_Up":
            return GestureIntent.THUMBS_UP
        if name == "Thumb_Down":
            return GestureIntent.UNCERTAINTY
    return None


class StableGestureGate:
    def __init__(self, *, stable_frames: int = 3, cooldown_seconds: float = 1.0) -> None:
        if stable_frames < 1:
            raise ValueError("stable_frames must be positive")
        self._samples: deque[GestureIntent | None] = deque(maxlen=stable_frames)
        self._stable_frames = stable_frames
        self._cooldown = cooldown_seconds
        self._latched: GestureIntent | None = None
        self._last_emit = float("-inf")

    def observe(
        self, intent: GestureIntent | None, *, now: float | None = None
    ) -> GestureIntent | None:
        timestamp = time.monotonic() if now is None else now
        self._samples.append(intent)
        if intent is None:
            self._latched = None
            return None
        if self._latched is not None or len(self._samples) < self._stable_frames:
            return None
        if not all(sample == intent for sample in self._samples):
            return None
        if timestamp - self._last_emit < self._cooldown:
            return None
        self._latched, self._last_emit = intent, timestamp
        return intent


def _redirect_native_output(log_path: str) -> None:
    path = Path(log_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.dup2(descriptor, 1)
        os.dup2(descriptor, 2)
    finally:
        os.close(descriptor)


def _classify_results(hand_result: Any) -> GestureIntent | None:
    for gestures in getattr(hand_result, "gestures", ()):
        intent = classify_gesture([(item.category_name, float(item.score)) for item in gestures])
        if intent is not None:
            return intent
    return None


def _gesture_worker(
    send: Callable[[tuple[Any, ...]], None],
    should_stop: Callable[[], bool],
    gesture_model: str,
    camera_index: int,
    log_path: str,
) -> None:
    """Own the only camera stream; redirect native output before runtime imports."""
    _redirect_native_output(log_path)
    capture: Any | None = None
    try:
        try:
            import cv2  # type: ignore[import-not-found]
            import mediapipe as mp  # type: ignore[import-not-found]
        except ImportError as exc:
            send(("error", GestureFailure.DEPENDENCY_MISSING.value, str(exc)))
            return
        capture = cv2.VideoCapture(camera_index, cv2.CAP_AVFOUNDATION)
        if not capture.isOpened():
            send(
                (
                    "error",
                    GestureFailure.CAMERA_UNAVAILABLE.value,
                    f"camera index {camera_index} unavailable or permission denied",
                )
            )
            return
        base, vision = mp.tasks.BaseOptions, mp.tasks.vision
        hands = vision.GestureRecognizer.create_from_options(
            vision.GestureRecognizerOptions(base_options=base(model_asset_path=gesture_model))
        )
        send(("ready",))
        gate = StableGestureGate()
        last_preview = last_inference = float("-inf")
        with hands:
            while not should_stop():
                ok, frame = capture.read()
                if not ok:
                    send(
                        (
                            "error",
                            GestureFailure.CAMERA_UNAVAILABLE.value,
                            "camera stopped returning frames",
                        )
                    )
                    return
                now = time.monotonic()
                if now - last_preview >= PREVIEW_INTERVAL_SECONDS:
                    height, width = frame.shape[:2]
                    preview_width = min(PREVIEW_PAYLOAD_WIDTH, width)
                    preview_height = max(1, round(height * preview_width / width))
                    preview = cv2.resize(
                        frame, (preview_width, preview_height), interpolation=cv2.INTER_AREA
                    )
                    preview = cv2.flip(preview, 1)  # Preview only; inference stays unmirrored.
                    rgb_preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB).tolist()
                    send(("preview", rgb_preview))
                    last_preview = now
                if now - last_inference < INFERENCE_INTERVAL_SECONDS:
                    continue
                last_inference = now
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                emitted = gate.observe(_classify_results(hands.recognize(image)))
                if emitted is not None:
                    send(("intent", emitted.value))
    except Exception as exc:
        send(("error", GestureFailure.RUNTIME_FAILED.value, str(exc)))
    finally:
        if capture is not None:
            capture.release()


class OpenCVMediaPipeGestureAdapter:
    def __init__(
        self,
        *,
        pose_model: Path | None = None,
        gesture_model: Path | None = None,
        camera_index: int | None = None,
        log_path: Path | None = None,
    ) -> None:
        settings = get_settings()
        # Retained as a no-op constructor argument for callers configured before
        # uncertainty moved from pose geometry to Gesture Recognizer's Thumb_Down.
        _ = pose_model
        self._gesture_model = gesture_model or settings.gesture_model
        self._camera_index = settings.gesture_camera_index if camera_index is None else camera_index
        self._log_path = log_path or settings.gesture_log_path
        self._process: subprocess.Popen[str] | None = None
        self._monitor: threading.Thread | None = None
        self._preview_callback: Callable[[Frame], None] | None = None
        self._failure_callback: Callable[[GestureUnavailableError], None] | None = None

    def set_preview_callback(self, callback: Callable[[Frame], None] | None) -> None:
        self._preview_callback = callback

    def set_failure_callback(
        self, callback: Callable[[GestureUnavailableError], None] | None
    ) -> None:
        self._failure_callback = callback

    def start(self, callback: Callable[[GestureIntent], None]) -> None:
        if self._process is not None:
            return
        if self._gesture_model is None:
            raise GestureUnavailableError(
                "gesture model paths are not configured",
                failure=GestureFailure.MODEL_NOT_CONFIGURED,
            )
        if not self._gesture_model.is_file():
            raise GestureUnavailableError(
                "configured gesture model assets were not found",
                failure=GestureFailure.MODEL_ASSET_MISSING,
            )
        command = [
            sys.executable,
            "-m",
            "terminal_ui.gesture_worker",
            str(self._gesture_model),
            str(self._camera_index),
            str(self._log_path),
        ]
        try:
            process = subprocess.Popen(  # noqa: S603 - fixed interpreter/module command
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except (OSError, ValueError) as exc:
            raise GestureUnavailableError(f"could not launch gesture runtime: {exc}") from exc
        self._process = process
        message = self._read_message(timeout=10)
        if message is None:
            self.stop()
            raise GestureUnavailableError("gesture runtime timed out during startup")
        if message[0] == "error":
            self.stop()
            raise GestureUnavailableError(message[2], failure=GestureFailure(message[1]))
        if message[0] != "ready":
            self.stop()
            raise GestureUnavailableError("gesture runtime returned an invalid startup response")
        self._monitor = threading.Thread(target=self._monitor_worker, args=(callback,), daemon=True)
        self._monitor.start()

    def _read_message(self, *, timeout: float | None = None) -> tuple[Any, ...] | None:
        process = self._process
        if process is None or process.stdout is None:
            return None
        if timeout is not None:
            selector = selectors.DefaultSelector()
            try:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout):
                    return None
            finally:
                selector.close()
        line = process.stdout.readline()
        if not line:
            return None
        message = json.loads(line)
        return tuple(message)

    def _monitor_worker(self, callback: Callable[[GestureIntent], None]) -> None:
        try:
            while self._process is not None:
                message = self._read_message()
                if message is None:
                    self._report_worker_failure(
                        GestureUnavailableError("gesture worker exited unexpectedly")
                    )
                    return
                if message[0] == "intent":
                    callback(GestureIntent(message[1]))
                elif message[0] == "preview" and self._preview_callback is not None:
                    self._preview_callback(message[1])
                elif message[0] == "error":
                    self._report_worker_failure(
                        GestureUnavailableError(message[2], failure=GestureFailure(message[1]))
                    )
                    return
        except (json.JSONDecodeError, OSError, ValueError):
            if self._process is not None:
                self._report_worker_failure(
                    GestureUnavailableError("gesture worker connection closed unexpectedly")
                )

    def _report_worker_failure(self, error: GestureUnavailableError) -> None:
        self.stop()
        if self._failure_callback is not None:
            self._failure_callback(error)

    def stop(self) -> None:
        process, self._process = self._process, None
        if process is not None:
            if process.stdin is not None:
                try:
                    process.stdin.write("stop\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                process.stdin.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            if process.stdout is not None:
                process.stdout.close()
        monitor, self._monitor = self._monitor, None
        if monitor is not None and monitor is not threading.current_thread():
            monitor.join(timeout=1)
