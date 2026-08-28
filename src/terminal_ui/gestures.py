"""Local gesture recognition isolated from Textual in a child process."""

from __future__ import annotations

import multiprocessing
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
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
    GestureFailure.RUNTIME_FAILED: "Gesture runtime could not start",
}


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


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    visibility: float = 1.0


def classify_shrug(landmarks: Mapping[str, Point]) -> bool:
    required = (
        "left_shoulder",
        "right_shoulder",
        "left_elbow",
        "right_elbow",
        "left_wrist",
        "right_wrist",
    )
    if any(name not in landmarks or landmarks[name].visibility < 0.6 for name in required):
        return False
    ls, rs = landmarks["left_shoulder"], landmarks["right_shoulder"]
    le, re = landmarks["left_elbow"], landmarks["right_elbow"]
    lw, rw = landmarks["left_wrist"], landmarks["right_wrist"]
    shoulder_width = abs(rs.x - ls.x)
    if shoulder_width < 0.1:
        return False
    return (
        abs(lw.y - ls.y) < 0.35 * shoulder_width
        and abs(rw.y - rs.y) < 0.35 * shoulder_width
        and le.y > lw.y
        and re.y > rw.y
        and lw.x < le.x < ls.x
        and rw.x > re.x > rs.x
    )


def classify_thumb_up(categories: Sequence[tuple[str, float]], *, threshold: float = 0.7) -> bool:
    return any(name == "Thumb_Up" and score >= threshold for name, score in categories)


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


def _classify_results(pose_result: Any, hand_result: Any) -> GestureIntent | None:
    for gestures in getattr(hand_result, "gestures", ()):
        if classify_thumb_up([(item.category_name, float(item.score)) for item in gestures]):
            return GestureIntent.THUMBS_UP
    poses = getattr(pose_result, "pose_landmarks", ())
    if poses:
        names = {
            11: "left_shoulder",
            12: "right_shoulder",
            13: "left_elbow",
            14: "right_elbow",
            15: "left_wrist",
            16: "right_wrist",
        }
        points = {
            name: Point(poses[0][i].x, poses[0][i].y, poses[0][i].visibility)
            for i, name in names.items()
        }
        if classify_shrug(points):
            return GestureIntent.UNCERTAINTY
    return None


def _gesture_worker(
    connection: Connection,
    stop_event: Any,
    pose_model: str,
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
            connection.send(("error", GestureFailure.DEPENDENCY_MISSING.value, str(exc)))
            return
        capture = cv2.VideoCapture(camera_index, cv2.CAP_AVFOUNDATION)
        if not capture.isOpened():
            connection.send(
                (
                    "error",
                    GestureFailure.CAMERA_UNAVAILABLE.value,
                    f"camera index {camera_index} unavailable or permission denied",
                )
            )
            return
        base, vision = mp.tasks.BaseOptions, mp.tasks.vision
        pose = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(base_options=base(model_asset_path=pose_model))
        )
        hands = vision.GestureRecognizer.create_from_options(
            vision.GestureRecognizerOptions(base_options=base(model_asset_path=gesture_model))
        )
        connection.send(("ready",))
        gate = StableGestureGate()
        last_preview = last_inference = float("-inf")
        with pose, hands:
            while not stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    break
                now = time.monotonic()
                if now - last_preview >= 0.125:
                    height, width = frame.shape[:2]
                    preview_width = min(32, width)
                    preview_height = max(1, round(height * preview_width / width))
                    preview = cv2.resize(
                        frame, (preview_width, preview_height), interpolation=cv2.INTER_AREA
                    )
                    preview = cv2.flip(preview, 1)  # Preview only; inference stays unmirrored.
                    rgb_preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB).tolist()
                    connection.send(("preview", rgb_preview))
                    last_preview = now
                if now - last_inference < 0.1:
                    continue
                last_inference = now
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                emitted = gate.observe(
                    _classify_results(pose.detect(image), hands.recognize(image))
                )
                if emitted is not None:
                    connection.send(("intent", emitted.value))
    except Exception as exc:
        connection.send(("error", GestureFailure.RUNTIME_FAILED.value, str(exc)))
    finally:
        if capture is not None:
            capture.release()
        connection.close()


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
        self._pose_model = pose_model or settings.pose_model
        self._gesture_model = gesture_model or settings.gesture_model
        self._camera_index = settings.gesture_camera_index if camera_index is None else camera_index
        self._log_path = log_path or settings.gesture_log_path
        self._process: BaseProcess | None = None
        self._stop_event: Any | None = None
        self._connection: Connection | None = None
        self._monitor: threading.Thread | None = None
        self._preview_callback: Callable[[Frame], None] | None = None

    def set_preview_callback(self, callback: Callable[[Frame], None] | None) -> None:
        self._preview_callback = callback

    def start(self, callback: Callable[[GestureIntent], None]) -> None:
        if self._process is not None:
            return
        if self._pose_model is None or self._gesture_model is None:
            raise GestureUnavailableError(
                "gesture model paths are not configured",
                failure=GestureFailure.MODEL_NOT_CONFIGURED,
            )
        if not self._pose_model.is_file() or not self._gesture_model.is_file():
            raise GestureUnavailableError(
                "configured gesture model assets were not found",
                failure=GestureFailure.MODEL_ASSET_MISSING,
            )
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        stop_event = context.Event()
        process = context.Process(
            target=_gesture_worker,
            args=(
                child,
                stop_event,
                str(self._pose_model),
                str(self._gesture_model),
                self._camera_index,
                str(self._log_path),
            ),
            daemon=True,
        )
        process.start()
        child.close()
        if not parent.poll(10):
            stop_event.set()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
            parent.close()
            raise GestureUnavailableError("gesture runtime timed out during startup")
        message = parent.recv()
        if message[0] == "error":
            process.join(timeout=2)
            parent.close()
            raise GestureUnavailableError(message[2], failure=GestureFailure(message[1]))
        self._process, self._stop_event, self._connection = process, stop_event, parent
        self._monitor = threading.Thread(target=self._monitor_worker, args=(callback,), daemon=True)
        self._monitor.start()

    def _monitor_worker(self, callback: Callable[[GestureIntent], None]) -> None:
        connection = self._connection
        if connection is None:
            return
        try:
            while self._process is not None:
                if not connection.poll(0.2):
                    if self._process is not None and not self._process.is_alive():
                        return
                    continue
                message = connection.recv()
                if message[0] == "intent":
                    callback(GestureIntent(message[1]))
                elif message[0] == "preview" and self._preview_callback is not None:
                    self._preview_callback(message[1])
        except (EOFError, OSError):
            return

    def stop(self) -> None:
        process, self._process = self._process, None
        stop_event, self._stop_event = self._stop_event, None
        if stop_event is not None:
            stop_event.set()
        if process is not None:
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        monitor, self._monitor = self._monitor, None
        if monitor is not None and monitor is not threading.current_thread():
            monitor.join(timeout=1)
