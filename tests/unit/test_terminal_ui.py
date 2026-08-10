from terminal_ui.app import CompanionTerminal


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
