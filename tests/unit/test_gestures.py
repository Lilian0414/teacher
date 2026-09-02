import asyncio
import subprocess
from collections.abc import Callable
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from rich.text import Text

from terminal_ui.app import CompanionTerminal, GestureState, InteractionMode
from terminal_ui.gestures import (
    INFERENCE_INTERVAL_SECONDS,
    PREVIEW_INTERVAL_SECONDS,
    PREVIEW_PAYLOAD_WIDTH,
    PREVIEW_TARGET_FPS,
    GestureFailure,
    GestureIntent,
    GestureUnavailableError,
    OpenCVMediaPipeGestureAdapter,
    StableGestureGate,
    classify_gesture,
)
from terminal_ui.preview import LatestFrameBuffer, render_frame
from tests.unit.test_terminal_ui import MessageSink


class FakeGestureAdapter:
    def __init__(self, error: GestureUnavailableError | None = None) -> None:
        self.error = error
        self.callback: Callable[[GestureIntent], None] | None = None
        self.failure_callback: Callable[[GestureUnavailableError], None] | None = None
        self.stop_calls = 0

    def set_failure_callback(
        self, callback: Callable[[GestureUnavailableError], None] | None
    ) -> None:
        self.failure_callback = callback

    def start(self, callback: Callable[[GestureIntent], None]) -> None:
        if self.error:
            raise self.error
        self.callback = callback

    def stop(self) -> None:
        self.stop_calls += 1


def test_canned_gestures_map_to_review_intents_above_threshold() -> None:
    assert classify_gesture([("Thumb_Down", 0.9)]) == GestureIntent.UNCERTAINTY
    assert classify_gesture([("Thumb_Up", 0.9)]) == GestureIntent.THUMBS_UP
    assert classify_gesture([("Thumb_Down", 0.69), ("Open_Palm", 0.9)]) is None


def test_stability_noise_hold_release_and_cooldown() -> None:
    gate = StableGestureGate(stable_frames=3, cooldown_seconds=2)
    assert gate.observe(GestureIntent.UNCERTAINTY, now=0) is None
    assert gate.observe(None, now=0.1) is None
    assert gate.observe(GestureIntent.UNCERTAINTY, now=0.2) is None
    assert gate.observe(GestureIntent.UNCERTAINTY, now=0.3) is None
    assert gate.observe(GestureIntent.UNCERTAINTY, now=0.4) == GestureIntent.UNCERTAINTY
    assert gate.observe(GestureIntent.UNCERTAINTY, now=0.5) is None
    assert gate.observe(None, now=0.6) is None
    for now in (0.7, 0.8, 0.9):
        assert gate.observe(GestureIntent.UNCERTAINTY, now=now) is None
    assert gate.observe(None, now=2.5) is None
    assert gate.observe(GestureIntent.THUMBS_UP, now=2.6) is None
    assert gate.observe(GestureIntent.THUMBS_UP, now=2.7) is None
    assert gate.observe(GestureIntent.THUMBS_UP, now=2.8) == GestureIntent.THUMBS_UP


def test_preview_buffer_is_latest_only_and_throttled() -> None:
    frames = LatestFrameBuffer(max_fps=5)
    first = [[(1, 2, 3)]]
    second = [[(4, 5, 6)]]
    latest = [[(7, 8, 9)]]

    assert frames.publish(first, now=0)
    assert not frames.publish(second, now=0.1)
    assert frames.publish(latest, now=0.2)
    assert frames.take_latest() is latest
    assert frames.take_latest() is None


def test_preview_cadence_and_payload_are_modestly_bounded() -> None:
    assert PREVIEW_TARGET_FPS == 18.0
    assert PREVIEW_INTERVAL_SECONDS == pytest.approx(1 / 18)
    assert PREVIEW_PAYLOAD_WIDTH == 192
    assert INFERENCE_INTERVAL_SECONDS == 0.1
    assert INFERENCE_INTERVAL_SECONDS != PREVIEW_INTERVAL_SECONDS


def test_preview_rendering_downsamples_to_bounded_terminal_dimensions() -> None:
    frame = [
        [(255, 0, 0), (0, 255, 0)],
        [(0, 0, 255), (255, 255, 255)],
    ]

    rendered = render_frame(frame, width=3, height=2)

    assert rendered.plain.splitlines() == ["▀▀▀"]


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (GestureFailure.MODEL_NOT_CONFIGURED, "models are not configured"),
        (GestureFailure.MODEL_ASSET_MISSING, "model files are missing"),
        (GestureFailure.DEPENDENCY_MISSING, "support is not installed"),
        (GestureFailure.CAMERA_UNAVAILABLE, "Camera unavailable"),
    ],
)
def test_gesture_startup_failures_have_specific_learner_messages(
    failure: GestureFailure, message: str
) -> None:
    error = GestureUnavailableError("diagnostic detail", failure=failure)
    assert message in error.learner_message


def test_monitor_reports_post_start_worker_error() -> None:
    class AdapterWithWorkerError(OpenCVMediaPipeGestureAdapter):
        def _read_message(self, *, timeout: float | None = None) -> tuple[str, str, str]:
            return (
                "error",
                GestureFailure.CAMERA_UNAVAILABLE.value,
                "camera stopped returning frames",
            )

    class FinishedProcess:
        stdin = None
        stdout = None

        def wait(self, timeout: float) -> None:
            return None

    adapter = AdapterWithWorkerError()
    failures: list[GestureUnavailableError] = []
    adapter.set_failure_callback(failures.append)
    adapter._process = cast(Any, FinishedProcess())

    adapter._monitor_worker(lambda intent: None)

    assert len(failures) == 1
    assert failures[0].failure == GestureFailure.CAMERA_UNAVAILABLE
    assert str(failures[0]) == "camera stopped returning frames"
    assert adapter._process is None


def test_subprocess_launch_fd_failure_is_reported_without_leaking_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    pose_model = tmp_path / "pose.task"
    gesture_model = tmp_path / "gesture.task"
    pose_model.touch()
    gesture_model.touch()
    adapter = OpenCVMediaPipeGestureAdapter(
        pose_model=pose_model, gesture_model=gesture_model, log_path=tmp_path / "gesture.log"
    )

    def fail_launch(*args: Any, **kwargs: Any) -> None:
        raise ValueError("bad value(s) in fds_to_keep")

    monkeypatch.setattr(subprocess, "Popen", fail_launch)

    with pytest.raises(GestureUnavailableError, match="could not launch gesture runtime"):
        adapter.start(lambda intent: None)

    assert adapter._process is None


def test_widescreen_preview_preserves_aspect_ratio() -> None:
    frame = [[(0, 0, 0)] * 16 for _ in range(9)]
    rendered = render_frame(frame, width=24, height=8)
    assert len(rendered.plain.splitlines()) == 7
    assert all(len(line) == 24 for line in rendered.plain.splitlines())


def test_gesture_action_labels_use_stable_public_states() -> None:
    terminal = CompanionTerminal(gesture_adapter=FakeGestureAdapter())

    assert terminal._gesture_action_label() == "Gestures: Off"
    terminal._gestures_enabled = True
    terminal._gesture_status = GestureState.ON
    assert terminal._gesture_action_label() == "Gestures: On"
    terminal._gestures_enabled = False
    terminal._gesture_status = GestureState.UNAVAILABLE
    assert terminal._gesture_action_label() == "Gestures: Unavailable"
    terminal._gesture_status = cast(Any, "internal_status")
    assert terminal._gesture_action_label() == "Gestures: Unavailable"


@pytest.mark.asyncio
async def test_uncertainty_reuses_hint_without_answer_request_or_state_change() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.content == b""
        return httpx.Response(200, json={"command": "hint", "ok": True, "hints": ["First word"]})

    terminal = CompanionTerminal(gesture_adapter=FakeGestureAdapter())
    terminal._messages = cast(Any, MessageSink())
    terminal._enter_review("item-1", prompt="prompt")
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.handle_gesture(GestureIntent.UNCERTAINTY)

    assert paths == ["/v1/review/item-1/hint"]
    assert terminal._mode == InteractionMode.REVIEW
    assert terminal._active_review_item_id == "item-1"
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_correct_completion_waits_for_thumb_or_finish_and_incorrect_bypasses() -> None:
    correct = True

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"result": {"correct": correct, "complete": True, "next_question": None}}
        )

    terminal = CompanionTerminal(gesture_adapter=FakeGestureAdapter())
    terminal._messages = cast(Any, MessageSink())
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._enter_review("item-1")
    await terminal._submit_review_answer("answer")
    assert terminal._mode == InteractionMode.REVIEW_COMPLETE
    assert "Finish" in str(terminal._action_buttons[0].label)

    await terminal.handle_gesture(GestureIntent.UNCERTAINTY)
    assert terminal._mode == InteractionMode.REVIEW_COMPLETE
    await terminal.handle_gesture(GestureIntent.THUMBS_UP)
    assert cast(InteractionMode, terminal._mode) == InteractionMode.NORMAL

    correct = False
    terminal._enter_review("item-2")
    await terminal._submit_review_answer("wrong")
    assert cast(InteractionMode, terminal._mode) == InteractionMode.REVIEW
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_camera_unavailable_leaves_typed_review_and_finish_fallback_usable() -> None:
    terminal = CompanionTerminal(
        gesture_adapter=FakeGestureAdapter(GestureUnavailableError("camera denied"))
    )
    terminal._messages = cast(Any, MessageSink())
    terminal._enter_review("item-1")
    await terminal.action_toggle_gestures()
    assert terminal._gesture_status is GestureState.UNAVAILABLE
    assert terminal._mode == InteractionMode.REVIEW

    terminal._mode = InteractionMode.REVIEW_COMPLETE
    terminal._refresh_action_buttons()
    await terminal.action_finish_review()
    assert terminal._mode == InteractionMode.NORMAL
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_post_start_failure_deactivates_gestures_without_ending_review() -> None:
    adapter = FakeGestureAdapter()
    terminal = CompanionTerminal(gesture_adapter=adapter)
    terminal._messages = cast(Any, MessageSink())
    terminal._enter_review("item-1")
    await terminal.action_toggle_gestures()
    assert terminal._gestures_enabled
    assert adapter.failure_callback is not None

    error = GestureUnavailableError(
        "camera stopped returning frames", failure=GestureFailure.CAMERA_UNAVAILABLE
    )
    terminal._handle_gesture_failure(error)

    assert not terminal._gestures_enabled
    assert terminal._gesture_status is GestureState.UNAVAILABLE
    assert terminal._mode == InteractionMode.REVIEW
    assert "type or speak your answer" in str(terminal._review_feedback.renderable)
    await terminal._client.aclose()

@pytest.mark.asyncio
async def test_gesture_feedback_is_colored_coalesced_focus_safe_and_auto_dismissed() -> None:
    terminal = CompanionTerminal(gesture_adapter=FakeGestureAdapter())

    async def skip_startup() -> None:
        return None

    terminal.on_mount = skip_startup  # type: ignore[method-assign]
    async with terminal.run_test() as pilot:
        terminal._mode = InteractionMode.REVIEW
        terminal._active_review_item_id = None
        terminal._refresh_practice_panel()
        terminal._input.focus()
        await pilot.pause()

        await terminal.handle_gesture(GestureIntent.UNCERTAINTY)
        first_timer = terminal._gesture_feedback_timer
        assert first_timer is not None
        feedback = cast(Text, terminal._gesture_feedback.renderable)
        assert "👎" in str(feedback)
        assert "yellow" in str(feedback.style)
        assert terminal.focused is terminal._input

        await terminal.handle_gesture(GestureIntent.UNCERTAINTY)
        assert first_timer is not terminal._gesture_feedback_timer
        await asyncio.sleep(0)
        assert first_timer.cancelled()
        assert terminal.focused is terminal._input

        terminal._mode = InteractionMode.REVIEW_COMPLETE
        terminal.action_finish_review = AsyncMock()  # type: ignore[method-assign]
        await terminal.handle_gesture(GestureIntent.THUMBS_UP)
        feedback = cast(Text, terminal._gesture_feedback.renderable)
        assert "👍" in str(feedback)
        assert "green" in str(feedback.style)
        assert terminal.focused is terminal._input

        await asyncio.sleep(0.95)
        await pilot.pause()
        assert not terminal._gesture_feedback.display
        assert terminal.focused is terminal._input
