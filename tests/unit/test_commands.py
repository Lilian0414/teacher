from companion.commands.parser import CommandParser


def test_parse_busy_command() -> None:
    parsed = CommandParser().parse("/busy 30m")

    assert parsed.name == "busy"
    assert parsed.duration is not None


def test_parse_dnd_command() -> None:
    assert CommandParser().parse("/dnd").name == "dnd"


def test_parse_available_command() -> None:
    assert CommandParser().parse("/available").name == "available"


def test_parse_status_command() -> None:
    assert CommandParser().parse("/status").name == "status"


def test_unknown_command_returns_available_commands() -> None:
    parsed = CommandParser().parse("/unknown hello")

    assert parsed.name == "unknown"
    assert parsed.error is not None
    assert "/busy <duration>" in parsed.error


def test_parse_m2_memory_commands() -> None:
    remember = CommandParser().parse("/remember Andy is my classmate")
    memories = CommandParser().parse("/memories Andy")
    forget = CommandParser().parse("/forget abc12345 confirm")

    assert remember.name == "remember"
    assert remember.content == "Andy is my classmate"
    assert memories.name == "memories"
    assert memories.content == "Andy"
    assert forget.name == "forget"
    assert forget.content == "abc12345"
    assert forget.confirm is True


def test_parse_interactive_review_commands() -> None:
    assert CommandParser().parse("/review").name == "review"
    assert CommandParser().parse("/review quit").name == "review_quit"
    assert CommandParser().parse("/review later").name == "unknown"
