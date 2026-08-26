import asyncio
from typing import Any, cast

import httpx
import pytest
from textual.widgets import Input

from terminal_ui.app import CompanionTerminal, InteractionMode


class MessageSink:
    def __init__(self) -> None:
        self.values: list[str] = []

    def write(self, value: str) -> None:
        self.values.append(value)


def make_terminal() -> CompanionTerminal:
    terminal = CompanionTerminal()
    terminal._messages = cast(Any, MessageSink())
    return terminal


def assert_mode(terminal: CompanionTerminal, expected: InteractionMode) -> None:
    assert terminal._mode == expected


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
    assert requests == ["/v1/proactive/check", "/v1/proactive/invitations/invite-1/respond"]
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
    assert messages[-1] == "assistant: Rest well."
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
    assert "Tue, Aug 11 at 12:00 PM" in feedback
    assert "Complete" in feedback


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
    assert terminal._mode == InteractionMode.NORMAL
    assert any("Complete" in value for value in sink.values)
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
    assert any("You said: I skipped class today." in value for value in sink.values)
    assert any("assistant: That happens sometimes." in value for value in sink.values)


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
        "",
        "",
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
