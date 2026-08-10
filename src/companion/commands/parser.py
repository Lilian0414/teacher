from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from companion.commands.duration import parse_duration

CommandName = Literal[
    "busy",
    "dnd",
    "available",
    "status",
    "help",
    "hint",
    "say",
    "remember",
    "memories",
    "forget",
    "unknown",
]

AVAILABLE_COMMANDS = (
    "/busy <duration>, /dnd, /available, /status, "
    "/help <內容>, /hint <內容>, /say <中文>, "
    "/remember <內容>, /memories [關鍵字], /forget <id> [confirm]"
)


@dataclass(frozen=True)
class ParsedCommand:
    name: CommandName
    duration: timedelta | None = None
    content: str | None = None
    confirm: bool = False
    error: str | None = None


class CommandParser:
    def __init__(self, *, max_busy_duration: timedelta = timedelta(hours=24)) -> None:
        self._max_busy_duration = max_busy_duration

    def parse(self, raw: str) -> ParsedCommand:
        text = raw.strip()
        if not text.startswith("/"):
            return ParsedCommand(
                name="unknown",
                error=f"Only M0 commands are available: {AVAILABLE_COMMANDS}",
            )

        parts = text.split()
        command = parts[0].lower()
        if command == "/busy":
            if len(parts) != 2:
                return ParsedCommand(name="unknown", error="Usage: /busy <duration>")
            try:
                return ParsedCommand(
                    name="busy",
                    duration=parse_duration(parts[1], max_duration=self._max_busy_duration),
                )
            except ValueError as exc:
                return ParsedCommand(name="unknown", error=str(exc))

        if command == "/dnd" and len(parts) == 1:
            return ParsedCommand(name="dnd")

        if command == "/available" and len(parts) == 1:
            return ParsedCommand(name="available")

        if command == "/status" and len(parts) == 1:
            return ParsedCommand(name="status")

        language_commands: dict[str, CommandName] = {
            "/help": "help",
            "/hint": "hint",
            "/say": "say",
        }
        if command in language_commands:
            content = text[len(parts[0]) :].strip()
            if not content:
                return ParsedCommand(name="unknown", error=f"Usage: {command} <content>")
            return ParsedCommand(name=language_commands[command], content=content)

        if command == "/remember":
            content = text[len(parts[0]) :].strip()
            if not content:
                return ParsedCommand(name="unknown", error="Usage: /remember <content>")
            return ParsedCommand(name="remember", content=content)

        if command == "/memories":
            content = text[len(parts[0]) :].strip()
            return ParsedCommand(name="memories", content=content or None)

        if command == "/forget":
            if len(parts) not in {2, 3} or (len(parts) == 3 and parts[2].lower() != "confirm"):
                return ParsedCommand(
                    name="unknown",
                    error="Usage: /forget <memory_id> [confirm]",
                )
            return ParsedCommand(
                name="forget",
                content=parts[1],
                confirm=len(parts) == 3,
            )

        return ParsedCommand(
            name="unknown",
            error=f"Unknown command. Available commands: {AVAILABLE_COMMANDS}",
        )
