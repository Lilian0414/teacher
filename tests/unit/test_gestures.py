from collections.abc import Callable
from typing import Any, cast

import httpx
import pytest

from terminal_ui.app import CompanionTerminal, InteractionMode
from terminal_ui.gestures import (
    GestureIntent,
    GestureUnavailableError,
    Point,
    StableGestureGate,
    classify_shrug,
    classify_thumb_up,
)
from tests.unit.test_terminal_ui import MessageSink


class FakeGestureAdapter:
    def __init__(self, error: GestureUnavailableError | None = None) -> None:
        self.error = error
        self.callback: Callable[[GestureIntent], None] | None = None
        self.stop_calls = 0

    def start(self, callback: Callable[[GestureIntent], None]) -> None:
        if self.error:
            raise self.error
        self.callback = callback

    def stop(self) -> None:
        self.stop_calls += 1


def shrug_points() -> dict[str, Point]:
    return {
        "left_shoulder": Point(0.4, 0.4),
        "right_shoulder": Point(0.6, 0.4),
        "left_elbow": Point(0.3, 0.5),
        "right_elbow": Point(0.7, 0.5),
        "left_wrist": Point(0.2, 0.4),
        "right_wrist": Point(0.8, 0.4),
    }


def test_deterministic_gesture_classifiers_cover_positive_and_negative() -> None:
    assert classify_shrug(shrug_points())
    obscured = shrug_points() | {"left_wrist": Point(0.2, 0.4, visibility=0.2)}
    assert not classify_shrug(obscured)
    assert classify_thumb_up([("Thumb_Up", 0.9)])
    assert not classify_thumb_up([("Thumb_Up", 0.69), ("Open_Palm", 0.9)])


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


@pytest.mark.asyncio
async def test_shrug_reuses_hint_without_answer_request_or_state_change() -> None:
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
    assert cast(InteractionMode, terminal._mode) == InteractionMode.NORMAL
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_camera_unavailable_leaves_typed_review_and_finish_fallback_usable() -> None:
    terminal = CompanionTerminal(
        gesture_adapter=FakeGestureAdapter(GestureUnavailableError("camera denied"))
    )
    terminal._messages = cast(Any, MessageSink())
    terminal._enter_review("item-1")
    await terminal.action_toggle_gestures()
    assert terminal._gesture_status == "unavailable"
    assert terminal._mode == InteractionMode.REVIEW

    terminal._mode = InteractionMode.REVIEW_COMPLETE
    terminal._refresh_action_buttons()
    await terminal.action_finish_review()
    assert terminal._mode == InteractionMode.NORMAL
    await terminal._client.aclose()
