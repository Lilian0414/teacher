from typing import Any, cast

import httpx
import pytest

from terminal_ui.app import CompanionTerminal


class MessageSink:
    def __init__(self) -> None:
        self.values: list[str] = []

    def write(self, value: str) -> None:
        self.values.append(value)


def test_hint_is_rendered_as_a_bulleted_list() -> None:
    rendered = CompanionTerminal._format_command_result(
        {
            "command": "hint",
            "ok": True,
            "hints": ["exhausted", "worn out", "a long day"],
        }
    )

    assert rendered == "[hint]\n- exhausted\n- worn out\n- a long day"


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

    assert natural == "[help zh] 意思是：你是怎麼得知這件事的？"
    assert "[help correction]" not in natural
    assert unnatural.endswith("[help correction] I am very tired today.")


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

    assert started == "[review 1] 我很累 (expression)"
    assert "I am tired" not in started
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

    terminal = CompanionTerminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    sink = MessageSink()
    terminal._messages = cast(Any, sink)

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

    terminal = CompanionTerminal()
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

    terminal = CompanionTerminal()
    await terminal._client.aclose()
    terminal._client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    terminal._messages = cast(Any, MessageSink())
    terminal._active_review_item_id = "item-1"

    await terminal._send_command("/review quit")

    assert terminal._active_review_item_id is None
    assert paths == ["/v1/commands/execute"]
    await terminal._client.aclose()
