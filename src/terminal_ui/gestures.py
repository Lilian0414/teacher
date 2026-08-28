"""Optional, local-only gesture recognition for the review UI.

The deterministic classifiers and temporal gate have no camera dependencies.  The
OpenCV/MediaPipe adapter imports its optional runtime only when it is started.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from terminal_ui.preview import Frame


class GestureIntent(StrEnum):
    UNCERTAINTY = "uncertainty"
    THUMBS_UP = "thumbs_up"


class GestureUnavailableError(RuntimeError):
    """Raised when the optional local camera runtime cannot be started."""


class GestureAdapter(Protocol):
    def start(self, callback: Callable[[GestureIntent], None]) -> None: ...
    def stop(self) -> None: ...


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    visibility: float = 1.0


def classify_shrug(landmarks: Mapping[str, Point]) -> bool:
    """Classify a shoulder-level, bent-elbow, palms-up shrug geometry."""
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
    wrists_near_shoulders = (
        abs(lw.y - ls.y) < 0.35 * shoulder_width and abs(rw.y - rs.y) < 0.35 * shoulder_width
    )
    elbows_below_wrists = le.y > lw.y and re.y > rw.y
    hands_outside = lw.x < le.x < ls.x and rw.x > re.x > rs.x
    return wrists_near_shoulders and elbows_below_wrists and hands_outside


def classify_thumb_up(categories: Sequence[tuple[str, float]], *, threshold: float = 0.7) -> bool:
    """Use MediaPipe's hand gesture category rather than pose inference."""
    return any(name == "Thumb_Up" and score >= threshold for name, score in categories)


class StableGestureGate:
    """Emit once after stable frames, then require release and a cooldown."""

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
        self._latched = intent
        self._last_emit = timestamp
        return intent


def _model_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value).expanduser() if value else None


class OpenCVMediaPipeGestureAdapter:
    """Mac-first camera adapter with lazy optional imports and ephemeral frames."""

    def __init__(
        self,
        *,
        pose_model: Path | None = None,
        gesture_model: Path | None = None,
        camera_index: int = 0,
    ) -> None:
        self._pose_model = pose_model or _model_path("COMPANION_POSE_MODEL")
        self._gesture_model = gesture_model or _model_path("COMPANION_GESTURE_MODEL")
        self._camera_index = camera_index
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._preview_callback: Callable[[Frame], None] | None = None

    def set_preview_callback(self, callback: Callable[[Frame], None] | None) -> None:
        """Share ephemeral frames from the owned capture without another stream."""
        self._preview_callback = callback

    def start(self, callback: Callable[[GestureIntent], None]) -> None:
        if self._thread is not None:
            return
        if self._pose_model is None or self._gesture_model is None:
            raise GestureUnavailableError("gesture model paths are not configured")
        try:
            import cv2  # type: ignore[import-not-found]
            import mediapipe as mp  # type: ignore[import-not-found]
        except ImportError as exc:
            raise GestureUnavailableError("OpenCV and MediaPipe are not installed") from exc
        if not self._pose_model.is_file() or not self._gesture_model.is_file():
            raise GestureUnavailableError("configured gesture model assets were not found")
        capture = cv2.VideoCapture(self._camera_index)
        if not capture.isOpened():
            capture.release()
            raise GestureUnavailableError("camera is unavailable or permission was denied")
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, args=(cv2, mp, capture, callback), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2)

    def _run(
        self, cv2: Any, mp: Any, capture: Any, callback: Callable[[GestureIntent], None]
    ) -> None:
        gate = StableGestureGate()
        last_preview = float("-inf")
        last_inference = float("-inf")
        try:
            base = mp.tasks.BaseOptions
            vision = mp.tasks.vision
            pose = vision.PoseLandmarker.create_from_options(
                vision.PoseLandmarkerOptions(
                    base_options=base(model_asset_path=str(self._pose_model))
                )
            )
            hands = vision.GestureRecognizer.create_from_options(
                vision.GestureRecognizerOptions(
                    base_options=base(model_asset_path=str(self._gesture_model))
                )
            )
            with pose, hands:
                while not self._stop_event.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        break
                    now = time.monotonic()
                    preview_callback = self._preview_callback
                    if preview_callback is not None and now - last_preview >= 0.2:
                        preview = cv2.resize(frame, (24, 16), interpolation=cv2.INTER_AREA)
                        preview_callback(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB).tolist())
                        last_preview = now
                    if now - last_inference < 0.1:
                        continue
                    last_inference = now
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    pose_result = pose.detect(image)
                    hand_result = hands.recognize(image)
                    intent = self._classify_results(pose_result, hand_result)
                    emitted = gate.observe(intent)
                    if emitted is not None:
                        callback(emitted)
        finally:
            capture.release()

    @staticmethod
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
            landmarks = {
                name: Point(poses[0][index].x, poses[0][index].y, poses[0][index].visibility)
                for index, name in names.items()
            }
            if classify_shrug(landmarks):
                return GestureIntent.UNCERTAINTY
        return None
