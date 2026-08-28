import asyncio
import os
import sys
import time
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from rich.console import Console
from rich.markdown import Markdown
from textual.widgets import Input

from companion.settings import get_settings
from terminal_ui.app import CompanionTerminal, InteractionMode
from terminal_ui.recording import MacMicrophoneRecorder, MicrophoneUnavailableError


class FakeRecorder:
    def __init__(self, result: bytes = b"wave", error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.start_calls = 0
        self.stop_calls = 0
        self.cancel_calls = 0

    async def start(self) -> None:
        self.start_calls += 1
        if self.error is not None:
            raise self.error

    async def stop(self) -> bytes:
        self.stop_calls += 1
        return self.result

    async def cancel(self) -> None:
        self.cancel_calls += 1


class MessageSink:
    def __init__(self) -> None:
        self.values: list[Any] = []

    def write(self, value: Any) -> None:
        self.values.append(value)


def render(value: object) -> str:
    if isinstance(value, str):
        return value
    console = Console(record=True, width=100, color_system=None)
    console.print(value)
    return console.export_text().rstrip()


def make_terminal() -> CompanionTerminal:
    terminal = CompanionTerminal()
    terminal._messages = cast(Any, MessageSink())
    return terminal


@pytest.mark.asyncio
async def test_spoken_review_shows_transcript_and_submits_canonical_answer_once() -> None:
    requests: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, request.content))
        if request.url.path == "/v1/speech/transcriptions":
            return httpx.Response(200, json={"transcript": "I fell asleep."})
        if request.url.path == "/v1/review/item-1/answer":
            return httpx.Response(200, json={"result": {"correct": True}})
        raise AssertionError(request.url.path)

    recorder = FakeRecorder()
    terminal = CompanionTerminal(recorder=recorder)
    terminal._messages = cast(Any, MessageSink())
    terminal._enter_review("item-1")
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.action_record_answer()

    assert recorder.start_calls == 1
    assert requests == []
    assert [str(button.label) for button in terminal._action_buttons] == [
        "Stop & submit",
        "",
        "Cancel",
    ]

    await terminal.action_record_answer()

    assert recorder.stop_calls == 1
    assert [path for path, _ in requests] == [
        "/v1/speech/transcriptions",
        "/v1/review/item-1/answer",
    ]
    assert any(
        "🎤 I fell asleep." in str(value)
        for value in cast(MessageSink, terminal._messages).values
    )
    assert terminal._mode == InteractionMode.NORMAL
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_chinese_spoken_review_redirects_without_submitting_or_advancing() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/v1/speech/transcriptions":
            return httpx.Response(200, json={"transcript": "我今天真的很累"})
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    terminal._enter_review("item-1")
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal._transcribe_review_answer(b"wave")

    assert requests == ["/v1/speech/transcriptions"]
    assert terminal._mode == InteractionMode.REVIEW
    assert terminal._active_review_item_id == "item-1"
    assert any(
        "Please try saying that in English." in str(value)
        for value in cast(MessageSink, terminal._messages).values
    )
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_chinese_typed_review_redirects_without_request_or_advancing() -> None:
    terminal = make_terminal()
    terminal._enter_review("item-1")

    await terminal._submit_review_answer("我今天真的很累")

    assert terminal._mode == InteractionMode.REVIEW
    assert terminal._active_review_item_id == "item-1"
    assert any(
        "Please try saying that in English." in str(value)
        for value in cast(MessageSink, terminal._messages).values
    )
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_microphone_unavailable_keeps_review_for_typed_fallback() -> None:
    terminal = CompanionTerminal(
        recorder=FakeRecorder(error=MicrophoneUnavailableError("Microphone denied."))
    )
    terminal._messages = cast(Any, MessageSink())
    terminal._enter_review("item-1")

    await terminal.action_record_answer()

    assert terminal._mode == InteractionMode.REVIEW
    assert terminal._active_review_item_id == "item-1"
    assert any(
        "still type" in str(value) for value in cast(MessageSink, terminal._messages).values
    )
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_transcription_retry_creates_only_one_review_attempt() -> None:
    transcription_calls = 0
    answer_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal transcription_calls, answer_calls
        if request.url.path == "/v1/speech/transcriptions":
            transcription_calls += 1
            if transcription_calls == 1:
                return httpx.Response(429, json={"detail": "Rate limit reached"})
            return httpx.Response(200, json={"transcript": "Hello"})
        if request.url.path == "/v1/review/item-1/answer":
            answer_calls += 1
            return httpx.Response(200, json={"result": {"correct": True}})
        raise AssertionError(request.url.path)

    terminal = CompanionTerminal(recorder=FakeRecorder())
    terminal._messages = cast(Any, MessageSink())
    terminal._enter_review("item-1")
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.action_record_answer()
    await terminal.action_record_answer()
    assert terminal._mode == InteractionMode.REVIEW
    assert answer_calls == 0

    await terminal.action_record_answer()
    await terminal.action_record_answer()

    assert transcription_calls == 2
    assert answer_calls == 1
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_user_can_cancel_active_recording_without_transcription_or_answer() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        raise AssertionError("cancellation must not call Core")

    recorder = FakeRecorder()
    terminal = CompanionTerminal(recorder=recorder)
    terminal._messages = cast(Any, MessageSink())
    terminal._enter_review("item-1")
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.action_record_answer()
    assert terminal._waiting is False
    assert terminal._input.disabled is False
    assert [str(button.label) for button in terminal._action_buttons] == [
        "Stop & submit",
        "",
        "Cancel",
    ]

    await terminal.action_stop_recording()

    assert recorder.cancel_calls == 1
    assert requests == []
    assert terminal._mode == InteractionMode.REVIEW
    assert terminal._active_review_item_id == "item-1"
    assert terminal._waiting is False
    assert terminal._input.disabled is False
    assert [str(button.label) for button in terminal._action_buttons] == [
        "Speak answer",
        "Gestures: disabled",
        "Stop review",
    ]
    assert any(
        "still type" in str(value) for value in cast(MessageSink, terminal._messages).values
    )
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_recording_safety_timeout_submits_at_most_once() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/v1/speech/transcriptions":
            return httpx.Response(200, json={"transcript": "Timed answer"})
        if request.url.path == "/v1/review/item-1/answer":
            return httpx.Response(200, json={"result": {"correct": True}})
        raise AssertionError(request.url.path)

    recorder = FakeRecorder()
    terminal = CompanionTerminal(recorder=recorder, recording_limit_seconds=0.01)
    terminal._messages = cast(Any, MessageSink())
    terminal._enter_review("item-1")
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.action_record_answer()
    await asyncio.sleep(0.05)
    await terminal.action_record_answer()

    assert recorder.start_calls == 1
    assert recorder.stop_calls == 1
    assert requests == ["/v1/speech/transcriptions", "/v1/review/item-1/answer"]
    assert any(
        "safety limit" in str(value)
        for value in cast(MessageSink, terminal._messages).values
    )
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_mac_recorder_uses_raw_buffers_without_numpy_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RawStream:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs.keys() == {"samplerate", "channels", "dtype", "callback"}
            assert kwargs["samplerate"] == 10
            self.callback = cast(Any, kwargs["callback"])

        def start(self) -> None:
            self.callback(b"\x01\x00" * 2, 2, None, None)

        def stop(self) -> None:
            return None

        def close(self) -> None:
            return None

    sounddevice = SimpleNamespace(RawInputStream=RawStream)
    monkeypatch.setitem(sys.modules, "sounddevice", sounddevice)
    recorder = MacMicrophoneRecorder(sample_rate=10)

    await recorder.start()
    audio = await recorder.stop()

    assert audio.startswith(b"RIFF")
    assert b"\x01\x00\x01\x00" in audio
    assert not hasattr(sounddevice, "rec")


@pytest.mark.asyncio
async def test_mac_recorder_cancel_discards_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    class RawStream:
        def __init__(self, **kwargs: object) -> None:
            self.callback = cast(Any, kwargs["callback"])

        def start(self) -> None:
            self.callback(b"\x01\x00", 1, None, None)

        def stop(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawInputStream=RawStream))
    recorder = MacMicrophoneRecorder(sample_rate=10)

    await recorder.start()
    await recorder.cancel()

    assert await recorder.stop() == b""
    assert recorder.state == "cancelled"


def assert_mode(terminal: CompanionTerminal, expected: InteractionMode) -> None:
    assert terminal._mode == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(("configured_interval", "expected_interval"), [(None, 30), ("5", 5)])
async def test_on_mount_uses_configured_proactive_poll_interval(
    monkeypatch: pytest.MonkeyPatch,
    configured_interval: str | None,
    expected_interval: int,
) -> None:
    if configured_interval is None:
        monkeypatch.delenv("COMPANION_PROACTIVE_POLL_INTERVAL_SECONDS", raising=False)
    else:
        monkeypatch.setenv("COMPANION_PROACTIVE_POLL_INTERVAL_SECONDS", configured_interval)
    get_settings.cache_clear()
    terminal = make_terminal()
    scheduled: list[tuple[float, object]] = []

    def record_interval(interval: float, callback: object) -> None:
        scheduled.append((interval, callback))

    async def refresh_state() -> dict[str, object]:
        return {}

    async def do_nothing() -> None:
        return None

    monkeypatch.setattr(terminal, "set_interval", record_interval)
    monkeypatch.setattr(terminal, "refresh_state", refresh_state)
    monkeypatch.setattr(terminal, "_show_onboarding_if_needed", do_nothing)
    monkeypatch.setattr(terminal, "ensure_conversation", do_nothing)
    monkeypatch.setattr(terminal, "_startup_message", lambda state: "ready")

    try:
        await terminal.on_mount()
    finally:
        get_settings.cache_clear()
        await terminal._client.aclose()

    assert scheduled == [
        (5, terminal.refresh_state),
        (expected_interval, terminal.check_proactive_invitation),
    ]


@pytest.mark.asyncio
async def test_onboarding_offer_is_non_blocking_and_core_controls_repeat() -> None:
    should_offer = iter((True, False))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/preferences/onboarding/offer":
            assert request.method == "POST"
            return httpx.Response(200, json={"should_offer": next(should_offer)})
        if request.url.path == "/v1/conversations/conversation-1/messages":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "user_message": {"id": "user-1"},
                    "assistant_message": {"id": "assistant-1", "content": "Hello!"},
                },
            )
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    messages = cast(MessageSink, terminal._messages)
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal._show_onboarding_if_needed()
    assert len(messages.values) == 1
    assert "keep chatting" in messages.values[0]
    assert "correction" in messages.values[0]
    assert "use defaults, or skip" in messages.values[0]
    assert terminal._mode == InteractionMode.NORMAL

    terminal._conversation_id = "conversation-1"
    await terminal._send_chat_message("Hello")
    assert any(render(value) == "assistant: Hello!" for value in messages.values)

    await terminal._show_onboarding_if_needed()
    assert sum("keep chatting" in render(message) for message in messages.values) == 1
    assert terminal._mode == InteractionMode.NORMAL
    await terminal._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "method", "path", "expected_message"),
    [
        ("onboarding-save", "PATCH", "/v1/preferences", "Preferences saved."),
        ("onboarding-defaults", "POST", "/v1/preferences/reset", "Using default preferences."),
        ("onboarding-skip", "POST", "/v1/preferences/reset", "Setup skipped."),
    ],
)
async def test_onboarding_choices_defaults_and_skip(
    action: str, method: str, path: str, expected_message: str
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    terminal = make_terminal()
    messages = cast(MessageSink, terminal._messages)
    terminal._onboarding_corrections.value = "intensive"
    terminal._onboarding_cadence.value = "rare"
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal._complete_onboarding(action)

    assert [(request.method, request.url.path) for request in requests] == [(method, path)]
    if action == "onboarding-save":
        assert requests[0].content == b'{"correction_style":"intensive","proactive_cadence":"rare"}'
    assert expected_message in messages.values
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_preferences_onboard_restarts_and_displays_panel() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json={"should_offer": True})

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal._handle_preferences("/preferences onboard")

    assert requests == [("POST", "/v1/preferences/onboarding/restart")]
    assert terminal._onboarding.display is True
    assert any(
        "keep chatting" in message for message in cast(MessageSink, terminal._messages).values
    )
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_proactive_poll_and_conversation_acceptance_are_local_until_user_answers() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/v1/proactive/check":
            return httpx.Response(
                200,
                json={
                    "invitation": {
                        "id": "invite-1",
                        "kind": "conversation",
                        "status": "pending",
                        "created_at": "2026-08-21T12:00:00+00:00",
                        "starter_prompt": "What made you smile today?",
                    }
                },
            )
        if request.url.path == "/v1/conversations":
            return httpx.Response(200, json={"id": "conversation-1"})
        if request.url.path == "/v1/preferences":
            return httpx.Response(200, json={"sound_enabled": False})
        if request.url.path.endswith("/respond"):
            return httpx.Response(
                200,
                json={
                    "invitation": {
                        "id": "invite-1",
                        "kind": "conversation",
                        "status": "accepted",
                        "created_at": "2026-08-21T12:00:00+00:00",
                    },
                    "conversation_starter": "What made you smile today?",
                },
            )
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    await terminal.check_proactive_invitation()
    assert terminal._pending_invitation is not None
    await terminal._respond_to_invitation("start")
    assert terminal._mode == InteractionMode.PRACTICE_PROMPT
    assert requests == [
        "/v1/proactive/check",
        "/v1/preferences",
        "/v1/conversations",
        "/v1/proactive/invitations/invite-1/respond",
    ]
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_practice_chat_is_finalized_once_with_returned_message_ids() -> None:
    requests: list[tuple[str, dict[str, Any] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content) if request.content else None
        requests.append((request.url.path, payload))
        if request.url.path == "/v1/conversations/conversation-1/messages":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "user_message": {"id": "user-1"},
                    "assistant_message": {"id": "assistant-1", "content": "Nice answer."},
                },
            )
        if request.url.path.endswith("/practice/complete"):
            return httpx.Response(200, json={"outcome": "completed_not_evaluated"})
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._conversation_id = "conversation-1"
    terminal._active_practice_invitation_id = "invite-1"
    terminal._mode = InteractionMode.PRACTICE_PROMPT

    await terminal._send_chat_message("My weekend was restful.")

    assert requests[1] == (
        "/v1/proactive/invitations/invite-1/practice/complete",
        {
            "conversation_id": "conversation-1",
            "user_message_id": "user-1",
            "assistant_message_id": "assistant-1",
        },
    )
    assert terminal._active_practice_invitation_id is None
    assert "Practice complete. This conversation was not graded." in terminal._messages.values
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_practice_partial_failure_retries_original_message_and_finalizes_once() -> None:
    requests: list[tuple[str, dict[str, Any] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content) if request.content else None
        requests.append((request.url.path, payload))
        if request.url.path == "/v1/conversations/conversation-1/messages":
            return httpx.Response(
                200,
                json={
                    "ok": False,
                    "user_message": {"id": "original-user"},
                    "assistant_message": None,
                    "error": "Assistant unavailable",
                    "retryable": True,
                },
            )
        if request.url.path.endswith("/retry-assistant"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "user_message": {"id": "original-user"},
                    "assistant_message": {"id": "assistant-1", "content": "Nice answer."},
                    "error": None,
                    "retryable": False,
                },
            )
        if request.url.path.endswith("/practice/complete"):
            return httpx.Response(200, json={"outcome": "completed_not_evaluated"})
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._conversation_id = "conversation-1"
    terminal._active_practice_invitation_id = "invite-1"
    terminal._mode = InteractionMode.PRACTICE_PROMPT

    await terminal._send_chat_message("My original answer.")

    assert terminal._pending_assistant_retry == {
        "conversation_id": "conversation-1",
        "user_message_id": "original-user",
        "invitation_id": "invite-1",
    }
    assert terminal._mode_button_specs()[0] == ("Retry reply", "retry_assistant")
    assert terminal.check_action("retry_assistant", ()) is True

    await terminal._retry_assistant_reply()

    assert requests == [
        ("/v1/conversations/conversation-1/messages", {"content": "My original answer."}),
        (
            "/v1/conversations/conversation-1/messages/original-user/retry-assistant",
            None,
        ),
        (
            "/v1/proactive/invitations/invite-1/practice/complete",
            {
                "conversation_id": "conversation-1",
                "user_message_id": "original-user",
                "assistant_message_id": "assistant-1",
            },
        ),
    ]
    assert terminal._pending_assistant_retry is None
    assert terminal._active_practice_invitation_id is None
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_ordinary_partial_failure_offers_retry_for_persisted_message() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                200,
                json={
                    "ok": False,
                    "user_message": {"id": "original-user"},
                    "assistant_message": None,
                    "error": "Assistant unavailable",
                    "retryable": True,
                },
            )
        return httpx.Response(
            200,
            json={
                "ok": True,
                "user_message": {"id": "original-user"},
                "assistant_message": {"id": "assistant-1", "content": "Recovered."},
                "error": None,
                "retryable": False,
            },
        )

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._conversation_id = "conversation-1"

    await terminal._send_chat_message("Persist this once.")
    assert terminal._pending_assistant_retry == {
        "conversation_id": "conversation-1",
        "user_message_id": "original-user",
    }
    assert "Your message was saved" in cast(MessageSink, terminal._messages).values[-1]

    await terminal._retry_assistant_reply()

    assert requests == [
        "/v1/conversations/conversation-1/messages",
        "/v1/conversations/conversation-1/messages/original-user/retry-assistant",
    ]
    assert terminal._pending_assistant_retry is None
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_practice_finalization_retry_does_not_resend_chat() -> None:
    requests: list[tuple[str, dict[str, Any] | None]] = []
    completion_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal completion_attempts
        payload = __import__("json").loads(request.content) if request.content else None
        requests.append((request.url.path, payload))
        if request.url.path == "/v1/conversations/conversation-1/messages":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "user_message": {"id": "user-1"},
                    "assistant_message": {"id": "assistant-1", "content": "Nice answer."},
                },
            )
        if request.url.path.endswith("/practice/complete"):
            completion_attempts += 1
            if completion_attempts == 1:
                return httpx.Response(503, json={"detail": "Try again"})
            return httpx.Response(200, json={"outcome": "completed_not_evaluated"})
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._conversation_id = "conversation-1"
    terminal._active_practice_invitation_id = "invite-1"
    terminal._mode = InteractionMode.PRACTICE_PROMPT

    with pytest.raises(httpx.HTTPStatusError):
        await terminal._send_chat_message("My weekend was restful.")

    assert_mode(terminal, InteractionMode.PRACTICE_PROMPT)
    assert terminal._active_practice_invitation_id == "invite-1"
    assert terminal._pending_practice_completion is not None

    await terminal._send_chat_message("This input must not become another message.")

    message_requests = [request for request in requests if request[0].endswith("/messages")]
    completion_requests = [
        request for request in requests if request[0].endswith("/practice/complete")
    ]
    assert len(message_requests) == 1
    assert [payload for _, payload in completion_requests] == [
        {
            "conversation_id": "conversation-1",
            "user_message_id": "user-1",
            "assistant_message_id": "assistant-1",
        },
        {
            "conversation_id": "conversation-1",
            "user_message_id": "user-1",
            "assistant_message_id": "assistant-1",
        },
    ]
    assert_mode(terminal, InteractionMode.NORMAL)
    assert terminal._active_practice_invitation_id is None
    assert terminal._pending_practice_completion is None
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_skip_practice_persists_abandonment_before_resetting_ui() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/practice/abandon")
        return httpx.Response(200, json={"status": "abandoned", "outcome": "abandoned"})

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._active_practice_invitation_id = "invite-1"
    terminal._mode = InteractionMode.PRACTICE_PROMPT

    await terminal.action_cancel_intent()

    assert terminal._mode == InteractionMode.NORMAL
    assert terminal._active_practice_invitation_id is None
    assert "Practice skipped." in terminal._messages.values
    await terminal._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("with_retry", [False, True])
async def test_quit_abandons_incomplete_practice_before_ending_conversation(
    with_retry: bool,
) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("/practice/abandon"):
            return httpx.Response(200, json={"status": "abandoned", "outcome": "abandoned"})
        if request.url.path.endswith("/end"):
            return httpx.Response(200, json={"conversation": {"ended_at": "now"}})
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._conversation_id = "conversation-1"
    terminal._active_practice_invitation_id = "invite-1"
    terminal._mode = InteractionMode.PRACTICE_PROMPT
    if with_retry:
        terminal._pending_assistant_retry = {
            "conversation_id": "conversation-1",
            "user_message_id": "saved-user",
            "invitation_id": "invite-1",
        }
    exited: list[bool] = []
    terminal.exit = lambda *args, **kwargs: exited.append(True)  # type: ignore[method-assign]

    await terminal.action_quit()

    assert requests == [
        "/v1/proactive/invitations/invite-1/practice/abandon",
        "/v1/conversations/conversation-1/end",
    ]
    assert terminal._active_practice_invitation_id is None
    assert terminal._pending_assistant_retry is None
    assert exited == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 503])
async def test_quit_finalizes_pending_evidence_and_stays_open_if_core_cannot_resolve(
    status: int,
) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("/practice/complete"):
            return httpx.Response(
                status,
                json=(
                    {"status": "completed", "outcome": "completed_not_evaluated"}
                    if status == 200
                    else {"detail": "offline"}
                ),
            )
        if request.url.path.endswith("/end"):
            return httpx.Response(200, json={"conversation": {"ended_at": "now"}})
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._conversation_id = "conversation-1"
    terminal._active_practice_invitation_id = "invite-1"
    terminal._pending_practice_completion = {
        "invitation_id": "invite-1",
        "conversation_id": "conversation-1",
        "user_message_id": "user-1",
        "assistant_message_id": "assistant-1",
    }
    exited: list[bool] = []
    terminal.exit = lambda *args, **kwargs: exited.append(True)  # type: ignore[method-assign]

    await terminal.action_quit()

    if status == 200:
        assert requests == [
            "/v1/proactive/invitations/invite-1/practice/complete",
            "/v1/conversations/conversation-1/end",
        ]
        assert terminal._pending_practice_completion is None
        assert exited == [True]
    else:
        assert requests == ["/v1/proactive/invitations/invite-1/practice/complete"]
        assert terminal._pending_practice_completion is not None
        assert terminal._active_practice_invitation_id == "invite-1"
        assert exited == []
        assert "quit cancelled" in cast(MessageSink, terminal._messages).values[-1]
        await terminal._client.aclose()


@pytest.mark.asyncio
async def test_proactive_review_acceptance_enters_the_same_review_mode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/proactive/invitations/invite-1/respond":
            return httpx.Response(
                200,
                json={
                    "invitation": {
                        "id": "invite-1",
                        "kind": "review",
                        "status": "accepted",
                        "created_at": "2026-08-21T12:00:00+00:00",
                    },
                    "review_question": {
                        "id": "item-1",
                        "prompt": "我很累",
                        "kind": "expression",
                        "position": 1,
                    },
                },
            )
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._pending_invitation = {"id": "invite-1", "kind": "review"}

    await terminal._respond_to_invitation("start")

    assert terminal._mode == InteractionMode.REVIEW
    assert terminal._active_review_item_id == "item-1"
    assert terminal._input.placeholder == "Answer the review question..."
    await terminal._client.aclose()


def test_hint_is_rendered_without_debug_prefix() -> None:
    rendered = CompanionTerminal._format_command_result(
        {
            "command": "hint",
            "ok": True,
            "hints": ["exhausted", "worn out", "a long day"],
        }
    )

    assert rendered == "Hints\n- exhausted\n- worn out\n- a long day"
    assert "[hint]" not in rendered


def test_english_help_only_shows_correction_when_present() -> None:
    natural = CompanionTerminal._format_command_result(
        {
            "command": "help",
            "ok": True,
            "notes_zh": "意思是：你是怎麼得知這件事的？",
            "correction": None,
        }
    )
    unnatural = CompanionTerminal._format_command_result(
        {
            "command": "help",
            "ok": True,
            "notes_zh": "原句缺少 be 動詞。",
            "correction": "I am very tired today.",
        }
    )

    assert natural == "Note\n意思是：你是怎麼得知這件事的？"
    assert "Suggested correction" not in natural
    assert unnatural.endswith("Suggested correction: I am very tired today.")
    assert "[help" not in natural
    assert "[help" not in unnatural


def test_help_renders_natural_expression_alternative_and_note() -> None:
    rendered = CompanionTerminal._format_command_result(
        {
            "command": "help",
            "ok": True,
            "natural_expression": "I skipped class today.",
            "alternatives": ["I ditched class today."],
            "notes_zh": "「skip class」是比較自然、中性的說法。",
        }
    )

    assert rendered == (
        "Natural expression\n"
        "I skipped class today.\n"
        "\n"
        "Alternative\n"
        "I ditched class today.\n"
        "\n"
        "Note\n"
        "「skip class」是比較自然、中性的說法。"
    )
    for prefix in ("[help]", "[help alt]", "[help zh]", "[help correction]"):
        assert prefix not in rendered


def test_say_result_has_no_debug_prefix() -> None:
    rendered = CompanionTerminal._format_command_result(
        {
            "command": "say",
            "ok": True,
            "inserted_text": "I skipped class today.",
            "assistant_message": {"content": "That happens to everyone sometimes."},
        }
    )

    assert "[say] inserted" not in rendered
    assert "You said: I skipped class today." in rendered
    assert "assistant: That happens to everyone sometimes." in rendered


@pytest.mark.asyncio
async def test_say_partial_retry_preserves_evidence_until_assistant_succeeds() -> None:
    requests: list[str] = []
    retry_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal retry_attempts
        requests.append(request.url.path)
        if request.url.path == "/v1/commands/execute":
            return httpx.Response(
                200,
                json={
                    "command": "say",
                    "ok": False,
                    "message": "Inserted translated English into the conversation.",
                    "inserted_into_conversation": True,
                    "inserted_text": "I am tired today.",
                    "inserted_user_message": {"id": "user-1"},
                    "assistant_error": "Assistant unavailable",
                    "retryable": True,
                },
            )
        if request.url.path.endswith("/retry-assistant"):
            retry_attempts += 1
            if retry_attempts == 1:
                return httpx.Response(
                    200,
                    json={
                        "ok": False,
                        "user_message": {"id": "user-1"},
                        "assistant_message": None,
                        "error": "Still unavailable",
                        "retryable": True,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "user_message": {"id": "user-1"},
                    "assistant_message": {"id": "assistant-1", "content": "Rest well."},
                    "error": None,
                    "retryable": False,
                },
            )
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._conversation_id = "conversation-1"

    await terminal._send_command("/say 今天很累")
    assert terminal._pending_assistant_retry == {
        "conversation_id": "conversation-1",
        "user_message_id": "user-1",
    }
    messages = cast(MessageSink, terminal._messages).values
    assert "You said: I am tired today." in messages[-1]
    assert "Assistant reply failed: Assistant unavailable" in messages[-1]

    await terminal._retry_assistant_reply()
    assert terminal._pending_assistant_retry is not None
    await terminal._retry_assistant_reply()
    assert terminal._pending_assistant_retry is None
    assert render(messages[-1]) == "assistant: Rest well."
    assert requests == [
        "/v1/commands/execute",
        "/v1/conversations/conversation-1/messages/user-1/retry-assistant",
        "/v1/conversations/conversation-1/messages/user-1/retry-assistant",
    ]
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_say_retry_conflict_shows_detail_and_clears_evidence() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/v1/commands/execute":
            return httpx.Response(
                200,
                json={
                    "command": "say",
                    "ok": False,
                    "inserted_text": "I am tired today.",
                    "inserted_user_message": {"id": "user-1"},
                    "assistant_error": "Assistant unavailable",
                    "retryable": True,
                },
            )
        if request.url.path.endswith("/retry-assistant"):
            return httpx.Response(
                409,
                json={"detail": "The retry target is stale because newer activity exists."},
            )
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._conversation_id = "conversation-1"

    await terminal._send_command("/say 今天很累")
    await terminal._retry_assistant_reply()

    assert terminal._pending_assistant_retry is None
    messages = cast(MessageSink, terminal._messages).values
    assert messages[-1] == "[system] The retry target is stale because newer activity exists."
    assert requests == [
        ("POST", "/v1/commands/execute"),
        (
            "POST",
            "/v1/conversations/conversation-1/messages/user-1/retry-assistant",
        ),
    ]
    assert all(path != "/v1/messages" for _, path in requests)
    await terminal._client.aclose()


def test_startup_message_shows_provider_without_api_key() -> None:
    rendered = CompanionTerminal._startup_message(
        {
            "llm": {
                "provider": "groq",
                "model": "test-model",
                "status": "key_present_unverified",
            }
        }
    )

    assert rendered == ("[system] Companion UI ready. LLM: groq/test-model/key_present_unverified.")
    assert "API" not in rendered


def test_memory_list_and_forget_confirmation_are_rendered() -> None:
    memory = {
        "short_id": "abc12345",
        "category": "people",
        "confidence": 0.9,
        "content": "Andy is my classmate.",
    }
    listed = CompanionTerminal._format_command_result(
        {"command": "memories", "ok": True, "memories": [memory]}
    )
    preview = CompanionTerminal._format_command_result(
        {
            "command": "forget",
            "ok": True,
            "memory": memory,
            "confirmation_required": True,
            "message": "Confirm deletion with /forget abc12345 confirm",
        }
    )

    assert "abc12345 | people | confidence=0.90" in listed
    assert "/forget abc12345 confirm" in preview


def test_review_question_and_feedback_are_rendered_without_early_answers() -> None:
    question = {
        "id": "item-1",
        "prompt": "我很累",
        "kind": "expression",
        "position": 1,
        "total": 2,
        "remaining": 2,
    }
    started = CompanionTerminal._format_command_result(
        {"command": "review", "ok": True, "review_question": question}
    )
    feedback = CompanionTerminal._format_review_result(
        {
            "correct": False,
            "prompt": "我很累",
            "submitted_answer": "sleepy",
            "accepted_answers": ["I am tired."],
            "next_review_at": "2026-08-11T12:00:00+00:00",
            "next_question": None,
        }
    )

    assert started == "Review item 1 of 2 (2 remaining)\n我很累 (expression)"
    assert "I am tired" not in started
    assert "[review" not in started
    assert "Incorrect" in feedback
    assert "Prompt: 我很累" in feedback
    assert "Your answer: sleepy" in feedback
    assert "Tue, Aug 11 at 8:00 PM Asia/Taipei" in feedback
    assert "Complete" in feedback


@pytest.mark.parametrize("host_timezone", ["UTC", "Asia/Taipei"])
def test_review_time_uses_product_timezone_not_host_timezone(
    host_timezone: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_timezone = os.environ.get("TZ")
    try:
        monkeypatch.setenv("TZ", host_timezone)
        if hasattr(time, "tzset"):
            time.tzset()
        monkeypatch.setenv("COMPANION_TIMEZONE", "Asia/Taipei")
        get_settings.cache_clear()

        rendered = CompanionTerminal._format_review_time("2026-08-11T12:00:00+00:00")

        assert rendered == "Tue, Aug 11 at 8:00 PM Asia/Taipei"
    finally:
        if original_timezone is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", original_timezone)
        if hasattr(time, "tzset"):
            time.tzset()
        get_settings.cache_clear()


def test_review_time_changes_with_product_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPANION_TIMEZONE", "UTC")
    get_settings.cache_clear()
    utc_rendered = CompanionTerminal._format_review_time("2026-08-11T12:00:00+00:00")
    monkeypatch.setenv("COMPANION_TIMEZONE", "Asia/Taipei")
    get_settings.cache_clear()

    taipei_rendered = CompanionTerminal._format_review_time("2026-08-11T12:00:00+00:00")

    assert utc_rendered == "Tue, Aug 11 at 12:00 PM UTC"
    assert taipei_rendered == "Tue, Aug 11 at 8:00 PM Asia/Taipei"
    assert utc_rendered != taipei_rendered
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_review_state_survives_interleaved_command_and_advances_on_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/commands/execute":
            raw = request.content.decode()
            if "/review" in raw:
                return httpx.Response(
                    200,
                    json={
                        "command": "review",
                        "ok": True,
                        "review_question": {
                            "id": "item-1",
                            "prompt": "我很累",
                            "kind": "expression",
                            "position": 1,
                        },
                    },
                )
            return httpx.Response(200, json={"command": "status", "ok": True, "message": "ok"})
        return httpx.Response(
            200,
            json={
                "result": {
                    "correct": True,
                    "accepted_answers": ["I am tired."],
                    "stage": 1,
                    "next_review_at": "2026-08-11T12:00:00+00:00",
                    "next_question": None,
                    "complete": True,
                }
            },
        )

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    sink = cast(MessageSink, terminal._messages)

    await terminal._send_command("/review")
    assert terminal._active_review_item_id == "item-1"
    assert terminal._mode == InteractionMode.REVIEW
    assert terminal._input.placeholder == "Answer the review question..."
    await terminal._send_command("/status")
    assert terminal._active_review_item_id == "item-1"
    assert terminal._mode == InteractionMode.REVIEW
    await terminal._submit_review_answer("I am tired")
    assert terminal._active_review_item_id is None
    assert terminal._mode == InteractionMode.REVIEW_COMPLETE
    assert any("Complete" in value for value in sink.values)
    assert any("thumbs-up" in value for value in sink.values)
    await terminal.action_finish_review()
    assert terminal._mode == InteractionMode.NORMAL
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_review_network_failure_keeps_active_question() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._enter_review("item-1")
    with pytest.raises(httpx.ConnectError):
        await terminal._submit_review_answer("answer")
    assert terminal._active_review_item_id == "item-1"
    assert terminal._mode == InteractionMode.REVIEW
    assert terminal._input.placeholder == "Answer the review question..."
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_review_quit_clears_active_question_without_answer_request() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"command": "review_quit", "ok": True, "message": "Review stopped."},
        )

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._enter_review("item-1")

    await terminal.action_cancel_intent()

    assert terminal._active_review_item_id is None
    assert terminal._mode == InteractionMode.NORMAL
    assert terminal._input.placeholder == "Say something..."
    assert paths == ["/v1/commands/execute"]
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_status_bar_shows_due_review_indicator() -> None:
    terminal = make_terminal()
    await terminal._client.aclose()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "user_id": "default",
                "availability": "available",
                "override_expires_at": None,
                "timezone": "Asia/Taipei",
                "remaining_seconds": None,
                "llm": {
                    "provider": "fake",
                    "model": None,
                    "configured": True,
                    "status": "configured",
                },
                "due_review_count": 3,
            },
        )

    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.refresh_state()

    assert "3 items ready to review" in str(terminal._status.renderable)
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_status_bar_shows_up_to_date_when_no_items_due() -> None:
    terminal = make_terminal()
    await terminal._client.aclose()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "user_id": "default",
                "availability": "available",
                "override_expires_at": None,
                "timezone": "Asia/Taipei",
                "remaining_seconds": None,
                "llm": {
                    "provider": "fake",
                    "model": None,
                    "configured": True,
                    "status": "configured",
                },
                "due_review_count": 0,
            },
        )

    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.refresh_state()

    assert "up to date" in str(terminal._status.renderable)
    await terminal._client.aclose()


def test_proactive_summary_uses_core_reason_and_threshold() -> None:
    assert (
        CompanionTerminal._format_proactive_status(
            {
                "cadence": "normal",
                "reason": "insufficient_idle",
                "idle_threshold_seconds": 600,
                "due_review_count": 0,
            }
        )
        == "Proactive: Normal · May invite after about 10 minutes of inactivity."
    )
    assert "2 reviews due — next invite prioritizes review" in (
        CompanionTerminal._format_proactive_status(
            {"cadence": "frequent", "reason": "eligible", "due_review_count": 2}
        )
    )


def test_proactive_summary_distinguishes_runtime_policy_and_paused_ui() -> None:
    legacy = CompanionTerminal._format_proactive_status(
        {
            "cadence": "normal",
            "uses_legacy_policy": True,
            "reason": "insufficient_idle",
            "idle_threshold_seconds": 20,
            "due_review_count": 0,
        }
    )
    assert legacy.startswith("Proactive: Runtime default ·")
    assert "Proactive: Normal" not in legacy

    completed = CompanionTerminal._format_proactive_status(
        {
            "cadence": "frequent",
            "uses_legacy_policy": False,
            "reason": "ui_cannot_present",
            "due_review_count": 0,
        }
    )
    assert completed == ("Proactive: Frequent · Teacher won't interrupt the current activity.")
    assert "ready" not in completed


def test_proactive_action_confirmations_use_core_boundary() -> None:
    payload = {"invitation": {"suppress_until": "2026-08-21T17:42:00+00:00"}}
    assert "before 01:42" in CompanionTerminal._format_invitation_suppression(payload, "snooze")
    assert "until 01:42" in CompanionTerminal._format_invitation_suppression(
        payload, "dismiss_today"
    )


@pytest.mark.asyncio
async def test_help_intent_reuses_existing_help_behavior_and_offers_actions() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raw = request.content.decode()
        requests.append(raw)
        return httpx.Response(
            200,
            json={
                "command": "help",
                "ok": True,
                "natural_expression": "I skipped class today.",
                "alternatives": ["I ditched class today."],
                "notes_zh": "「skip class」是比較自然、中性的說法。",
            },
        )

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    sink = cast(MessageSink, terminal._messages)

    terminal._begin_capture(InteractionMode.AWAITING_HELP_SENTENCE)
    await terminal._run_guarded(lambda: terminal._run_help_capture("我今天翹課了"))

    assert '"raw":"/help 我今天翹課了"' in requests[0]
    assert terminal._mode == InteractionMode.HELP_RESULT
    assert terminal._pending_help_content == "我今天翹課了"
    assert terminal._pending_help_expression == "I skipped class today."
    assert any("Natural expression" in value for value in sink.values)
    assert any("Actions:" in value for value in sink.values)
    assert any("Use this" in value for value in sink.values)
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_hint_intent_creates_learning_item_and_does_not_offer_actions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"command": "hint", "ok": True, "hints": ["cut class", "ditch class"]},
        )

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    sink = cast(MessageSink, terminal._messages)

    terminal._begin_capture(InteractionMode.AWAITING_HINT_SENTENCE)
    await terminal._run_guarded(lambda: terminal._run_hint_capture("我今天翹課了"))

    assert terminal._mode == InteractionMode.NORMAL
    assert terminal._pending_help_content is None
    assert any("Hints" in value for value in sink.values)
    assert not any("Actions:" in value for value in sink.values)


@pytest.mark.asyncio
async def test_use_this_sends_the_exact_displayed_expression_without_retranslating() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, request.content.decode()))
        if request.url.path == "/v1/conversations/conv-1/messages":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "user_message": {
                        "id": "user-1",
                        "conversation_id": "conv-1",
                        "role": "user",
                        "content": "I skipped class today.",
                        "language": "en",
                        "source": "terminal",
                        "created_at": "2026-08-19T00:00:00+00:00",
                    },
                    "assistant_message": {
                        "id": "assistant-1",
                        "conversation_id": "conv-1",
                        "role": "assistant",
                        "content": "That happens sometimes.",
                        "language": "en",
                        "source": "terminal",
                        "created_at": "2026-08-19T00:00:01+00:00",
                    },
                    "error": None,
                    "retryable": False,
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    sink = cast(MessageSink, terminal._messages)
    terminal._conversation_id = "conv-1"
    terminal._mode = InteractionMode.HELP_RESULT
    terminal._pending_help_content = "我今天翹課了"
    terminal._pending_help_expression = "I skipped class today."

    await terminal.action_use_suggestion()

    assert requests == [
        (
            "/v1/conversations/conv-1/messages",
            '{"content":"I skipped class today."}',
        )
    ]
    assert terminal._mode == InteractionMode.NORMAL
    assert terminal._pending_help_content is None
    assert terminal._pending_help_expression is None
    assert any("You said: I skipped class today." in render(value) for value in sink.values)
    assert any("assistant: That happens sometimes." in render(value) for value in sink.values)


@pytest.mark.asyncio
async def test_hint_only_reuses_pending_content_without_leaving_help_result_dangling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"command": "hint", "ok": True, "hints": ["cut class"]},
        )

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    sink = cast(MessageSink, terminal._messages)
    terminal._mode = InteractionMode.HELP_RESULT
    terminal._pending_help_content = "我今天翹課了"

    await terminal.action_hint_intent()

    assert terminal._mode == InteractionMode.NORMAL
    assert any("Hints" in value for value in sink.values)


def test_try_myself_returns_to_normal_input_without_sending() -> None:
    terminal = make_terminal()
    sink = cast(MessageSink, terminal._messages)
    terminal._mode = InteractionMode.HELP_RESULT
    terminal._pending_help_content = "我今天翹課了"

    asyncio_run = pytest.importorskip("asyncio").run
    asyncio_run(terminal.action_cancel_intent())

    assert terminal._mode == InteractionMode.NORMAL
    assert terminal._pending_help_content is None
    assert terminal._pending_help_expression is None
    assert terminal._input.placeholder == "Say something..."
    assert any("try it yourself" in value for value in sink.values)


def test_action_buttons_relabel_for_help_result_mode() -> None:
    terminal = make_terminal()
    terminal._mode = InteractionMode.HELP_RESULT
    terminal._refresh_action_buttons()

    labels = [str(button.label) for button in terminal._action_buttons]
    assert labels == ["Use this", "Hint only", "Try myself"]


def test_action_buttons_show_primary_intents_in_normal_mode() -> None:
    terminal = make_terminal()
    terminal._refresh_action_buttons()

    labels = [str(button.label) for button in terminal._action_buttons]
    assert labels == ["Help me say it", "Give me a hint", "Review"]


def test_check_action_hides_primary_intents_mid_capture() -> None:
    terminal = make_terminal()
    terminal._mode = InteractionMode.AWAITING_HELP_SENTENCE

    assert terminal.check_action("help_intent", ()) is False
    assert terminal.check_action("hint_intent", ()) is False
    assert terminal.check_action("review_intent", ()) is False
    assert terminal.check_action("cancel_intent", ()) is True


def test_check_action_only_shows_use_suggestion_in_help_result() -> None:
    terminal = make_terminal()
    assert terminal.check_action("use_suggestion", ()) is False

    terminal._mode = InteractionMode.HELP_RESULT
    terminal._pending_help_expression = "I skipped class today."
    assert terminal.check_action("use_suggestion", ()) is True


@pytest.mark.asyncio
async def test_review_owns_input_and_blocks_help_or_hint_entry_points() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, request.content.decode()))
        if request.url.path == "/v1/review/item-1/answer":
            return httpx.Response(
                200,
                json={
                    "result": {
                        "correct": False,
                        "accepted_answers": ["Hello", "Hi", "Hey"],
                        "stage": 0,
                        "next_review_at": "2026-08-24T03:43:57+08:00",
                        "next_question": None,
                        "complete": True,
                    }
                },
            )
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._enter_review("item-1")

    await terminal.action_hint_intent()
    await terminal.action_help_intent()

    assert terminal._mode == InteractionMode.REVIEW
    assert terminal._active_review_item_id == "item-1"
    assert terminal._input.placeholder == "Answer the review question..."
    assert [str(button.label) for button in terminal._action_buttons] == [
        "Speak answer",
        "Gestures: disabled",
        "Stop review",
    ]
    assert requests == []

    await terminal.on_input_submitted(Input.Submitted(terminal._input, "love you"))

    assert requests == [
        (
            "/v1/review/item-1/answer",
            '{"answer":"love you","position":1,"total":1}',
        ),
    ]
    assert_mode(terminal, InteractionMode.NORMAL)
    assert terminal._active_review_item_id is None
    await terminal._client.aclose()


def test_terminal_uses_configured_core_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPANION_PORT", "9123")
    from companion.settings import get_settings

    get_settings.cache_clear()
    terminal = CompanionTerminal()
    assert terminal._core_url == "http://127.0.0.1:9123"
    asyncio.run(terminal._client.aclose())
    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(("sound_enabled", "expected_bells"), [(True, 1), (False, 0)])
async def test_presented_invitation_honors_sound_preference(
    monkeypatch: pytest.MonkeyPatch, sound_enabled: bool, expected_bells: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/proactive/check":
            return httpx.Response(
                200, json={"invitation": {"id": "invite-1", "kind": "conversation"}}
            )
        if request.url.path == "/v1/preferences":
            return httpx.Response(200, json={"sound_enabled": sound_enabled})
        raise AssertionError(request.url.path)

    terminal = make_terminal()
    bells: list[None] = []
    monkeypatch.setattr(terminal, "bell", lambda: bells.append(None))
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.check_proactive_invitation()

    assert terminal._pending_invitation is not None
    assert len(bells) == expected_bells
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_invitation_cue_is_deduplicated_by_id(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        assert request.url.path == "/v1/preferences"
        requests += 1
        return httpx.Response(200, json={"sound_enabled": True})

    terminal = make_terminal()
    bells: list[None] = []
    monkeypatch.setattr(terminal, "bell", lambda: bells.append(None))
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal._cue_invitation({"id": "invite-1"})
    await terminal._cue_invitation({"id": "invite-1"})

    assert len(bells) == 1
    assert requests == 1
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_preference_failure_is_silent_and_invitation_still_presents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/proactive/check":
            return httpx.Response(200, json={"invitation": {"id": "invite-1", "kind": "review"}})
        return httpx.Response(503)

    terminal = make_terminal()
    bells: list[None] = []
    monkeypatch.setattr(terminal, "bell", lambda: bells.append(None))
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.check_proactive_invitation()

    assert terminal._pending_invitation == {"id": "invite-1", "kind": "review"}
    assert terminal._invitation.display is True
    assert bells == []
    await terminal._client.aclose()


@pytest.mark.asyncio
async def test_no_presentable_invitation_does_not_fetch_preferences_or_bell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(200, json={"invitation": {"id": "invite-1", "kind": "review"}})

    terminal = make_terminal()
    terminal._waiting = True
    bells: list[None] = []
    monkeypatch.setattr(terminal, "bell", lambda: bells.append(None))
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    await terminal.check_proactive_invitation()

    assert requests == ["/v1/proactive/check"]
    assert terminal._pending_invitation is None
    assert bells == []
    await terminal._client.aclose()


def test_assistant_helper_writes_markdown_without_rewriting_source() -> None:
    terminal = make_terminal()
    source = "**Salmon** is a good choice."

    terminal._write_assistant(source)

    written = cast(MessageSink, terminal._messages).values[-1]
    assert isinstance(written, Markdown)
    assert render(written) == "assistant: Salmon is a good choice."
    assert source == "**Salmon** is a good choice."


@pytest.mark.asyncio
async def test_normal_chat_and_retry_share_assistant_rendering_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        content = "Normal **reply**." if requests == 1 else "Retried **reply**."
        return httpx.Response(
            200,
            json={
                "ok": True,
                "user_message": {"id": "user-1"},
                "assistant_message": {"id": f"assistant-{requests}", "content": content},
            },
        )

    terminal = make_terminal()
    rendered: list[str] = []
    monkeypatch.setattr(terminal, "_write_assistant", rendered.append)
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._conversation_id = "conversation-1"

    await terminal._send_chat_message("hello")
    terminal._pending_assistant_retry = {
        "conversation_id": "conversation-1",
        "user_message_id": "user-1",
    }
    await terminal._retry_assistant_reply()

    assert rendered == ["Normal **reply**.", "Retried **reply**."]
    await terminal._client.aclose()


def test_plain_user_and_system_writes_remain_literal() -> None:
    terminal = make_terminal()

    terminal._messages.write("You said: [red]hello[/red]")
    terminal._messages.write("[system] [red]hello[/red]")

    assert cast(MessageSink, terminal._messages).values == [
        "You said: [red]hello[/red]",
        "[system] [red]hello[/red]",
    ]
