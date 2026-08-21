from typing import Any, cast

import httpx
import pytest

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


@pytest.mark.asyncio
async def test_proactive_poll_and_conversation_acceptance_are_local_until_user_answers() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/v1/proactive/check":
            return httpx.Response(200, json={"invitation": {
                "id": "invite-1", "kind": "conversation", "status": "pending",
                "created_at": "2026-08-21T12:00:00+00:00",
                "starter_prompt": "What made you smile today?",
            }})
        if request.url.path.endswith("/respond"):
            return httpx.Response(200, json={
                "invitation": {"id": "invite-1", "kind": "conversation",
                               "status": "accepted", "created_at": "2026-08-21T12:00:00+00:00"},
                "conversation_starter": "What made you smile today?",
            })
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


def test_startup_message_shows_provider_without_api_key() -> None:
    rendered = CompanionTerminal._startup_message(
        {
            "llm": {
                "provider": "groq",
                "model": "test-model",
                "status": "configured",
            }
        }
    )

    assert rendered == "[system] M1 UI ready. LLM: groq/test-model/configured."
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
    question = {"id": "item-1", "prompt": "我很累", "kind": "expression", "position": 1}
    started = CompanionTerminal._format_command_result(
        {"command": "review", "ok": True, "review_question": question}
    )
    feedback = CompanionTerminal._format_review_result(
        {
            "correct": False,
            "accepted_answers": ["I am tired."],
            "next_review_at": "2026-08-11T12:00:00+00:00",
            "next_question": None,
        }
    )

    assert started == "Review item 1\n我很累 (expression)"
    assert "I am tired" not in started
    assert "[review" not in started
    assert "Incorrect" in feedback
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
    await terminal._send_command("/status")
    assert terminal._active_review_item_id == "item-1"
    await terminal._submit_review_answer("I am tired")
    assert terminal._active_review_item_id is None
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
    terminal._active_review_item_id = "item-1"
    with pytest.raises(httpx.ConnectError):
        await terminal._submit_review_answer("answer")
    assert terminal._active_review_item_id == "item-1"
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
    terminal._active_review_item_id = "item-1"

    await terminal._send_command("/review quit")

    assert terminal._active_review_item_id is None
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
    assert terminal.check_action("review_intent", ()) is False
    assert terminal.check_action("cancel_intent", ()) is True


def test_check_action_only_shows_use_suggestion_in_help_result() -> None:
    terminal = make_terminal()
    assert terminal.check_action("use_suggestion", ()) is False

    terminal._mode = InteractionMode.HELP_RESULT
    terminal._pending_help_expression = "I skipped class today."
    assert terminal.check_action("use_suggestion", ()) is True
