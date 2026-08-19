import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, cast

import httpx
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, RichLog, Static


class InteractionMode(StrEnum):
    """Tracks where the terminal is within the intent-based interaction flow.

    NORMAL is ordinary conversation (or slash-command) input. The two
    AWAITING_* modes capture the sentence the user wants help or a hint
    with. HELP_RESULT is the follow-up step after a successful "Help me
    say it" response, offering Use this / Hint only / Try myself.
    """

    NORMAL = "normal"
    AWAITING_HELP_SENTENCE = "awaiting_help_sentence"
    AWAITING_HINT_SENTENCE = "awaiting_hint_sentence"
    HELP_RESULT = "help_result"


class CompanionTerminal(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }
    #status {
        height: 3;
        padding: 0 1;
    }
    #messages {
        height: 1fr;
        border: solid $primary;
    }
    #actions {
        height: 3;
        padding: 0 1;
    }
    #actions Button {
        margin-right: 1;
    }
    #command {
        dock: bottom;
    }
    """

    # Exact key choices are flexible (see M3.5 issue): Ctrl+I is avoided
    # because most terminals report it identically to Tab, which would
    # silently break focus navigation instead of giving a hint shortcut.
    BINDINGS = [
        ("ctrl+h", "help_intent", "Help me say it"),
        ("ctrl+g", "hint_intent", "Hint"),
        ("ctrl+r", "review_intent", "Review"),
        ("ctrl+u", "use_suggestion", "Use this"),
        ("escape", "cancel_intent", "Try myself"),
    ]

    def __init__(self, core_url: str = "http://127.0.0.1:8000") -> None:
        super().__init__()
        self._core_url = core_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._core_url,
            timeout=40.0,
            trust_env=False,
        )
        self._status = Static(
            "Core: unknown | Availability: unknown | Remaining: - | LLM: unknown",
            id="status",
        )
        self._messages = RichLog(id="messages", wrap=True, markup=False)
        self._input = Input(
            placeholder="Say something...",
            id="command",
        )
        self._action_buttons: list[Button] = [
            Button(id="action-1"),
            Button(id="action-2"),
            Button(id="action-3"),
        ]
        self._button_actions: dict[str, str] = {}
        self._conversation_id: str | None = None
        self._active_review_item_id: str | None = None
        self._waiting = False
        self._mode = InteractionMode.NORMAL
        self._pending_help_content: str | None = None
        self._due_review_count = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield self._status
            yield self._messages
            with Horizontal(id="actions"):
                yield from self._action_buttons
            yield self._input
        yield Footer()

    async def on_mount(self) -> None:
        self._refresh_action_buttons()
        self.set_interval(5, self.refresh_state)
        state = await self.refresh_state()
        await self.ensure_conversation()
        self._messages.write(self._startup_message(state))

    # ------------------------------------------------------------------
    # Primary intents (Help me say it / Give me a hint / Review) and the
    # Use this / Hint only / Try myself follow-up to a help suggestion.
    # ------------------------------------------------------------------

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"help_intent", "review_intent"}:
            return self._mode == InteractionMode.NORMAL
        if action == "use_suggestion":
            return self._mode == InteractionMode.HELP_RESULT
        if action == "cancel_intent":
            return self._mode != InteractionMode.NORMAL
        return True

    async def action_help_intent(self) -> None:
        if self._waiting or self._mode != InteractionMode.NORMAL:
            return
        self._begin_capture(InteractionMode.AWAITING_HELP_SENTENCE)

    async def action_hint_intent(self) -> None:
        if self._waiting:
            return
        if self._mode == InteractionMode.HELP_RESULT:
            if self._pending_help_content is None:
                return
            await self._run_guarded(self._run_hint_only)
            return
        if self._mode != InteractionMode.NORMAL:
            return
        self._begin_capture(InteractionMode.AWAITING_HINT_SENTENCE)

    async def action_review_intent(self) -> None:
        if self._waiting or self._mode != InteractionMode.NORMAL:
            return
        await self._run_guarded(self._run_review_intent)

    async def action_use_suggestion(self) -> None:
        if (
            self._waiting
            or self._mode != InteractionMode.HELP_RESULT
            or self._pending_help_content is None
        ):
            return
        await self._run_guarded(self._run_use_suggestion)

    async def action_cancel_intent(self) -> None:
        if self._mode == InteractionMode.NORMAL:
            return
        was_help_result = self._mode == InteractionMode.HELP_RESULT
        self._reset_to_normal()
        if was_help_result:
            self._messages.write("Okay, try it yourself.")
        else:
            self._messages.write("Cancelled.")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._waiting:
            return
        action_name = self._button_actions.get(event.button.id or "")
        if action_name is None:
            return
        await self.run_action(action_name)

    async def _run_review_intent(self) -> None:
        await self._send_command("/review")

    async def _run_use_suggestion(self) -> None:
        content = self._pending_help_content
        assert content is not None
        await self._send_command(f"/say {content}")
        self._reset_to_normal()

    async def _run_hint_only(self) -> None:
        content = self._pending_help_content
        if content is None:
            return
        result = await self._post_command(f"/hint {content}")
        self._messages.write(self._format_command_result(result))
        self._reset_to_normal()

    async def _run_help_capture(self, raw: str) -> None:
        self._pending_help_content = raw
        result = await self._post_command(f"/help {raw}")
        self._messages.write(self._format_command_result(result))
        if result.get("ok") and result.get("command") == "help":
            self._mode = InteractionMode.HELP_RESULT
            self._after_mode_change()
            self._messages.write("Actions:\n- Use this\n- Hint only\n- Try myself")
        else:
            self._reset_to_normal()

    async def _run_hint_capture(self, raw: str) -> None:
        result = await self._post_command(f"/hint {raw}")
        self._messages.write(self._format_command_result(result))
        self._reset_to_normal()

    def _begin_capture(self, mode: InteractionMode) -> None:
        self._mode = mode
        self._pending_help_content = None
        self._input.placeholder = "What do you want to say?"
        self._messages.write("What do you want to say?")
        self._after_mode_change()
        self._focus_input()

    def _reset_to_normal(self) -> None:
        self._mode = InteractionMode.NORMAL
        self._pending_help_content = None
        self._input.placeholder = "Say something..."
        self._after_mode_change()
        self._focus_input()

    def _after_mode_change(self) -> None:
        self._refresh_action_buttons()
        if self.is_running:
            self.refresh_bindings()

    def _focus_input(self) -> None:
        if self.is_running:
            self._input.focus()

    def _refresh_action_buttons(self) -> None:
        specs = self._mode_button_specs()
        actions: dict[str, str] = {}
        for button, spec in zip(self._action_buttons, specs, strict=True):
            if spec is None:
                button.label = ""
                button.disabled = True
                continue
            label, action_name = spec
            button.label = label
            button.disabled = False
            if button.id is not None:
                actions[button.id] = action_name
        self._button_actions = actions

    def _mode_button_specs(self) -> list[tuple[str, str] | None]:
        if self._mode == InteractionMode.HELP_RESULT:
            return [
                ("Use this", "use_suggestion"),
                ("Hint only", "hint_intent"),
                ("Try myself", "cancel_intent"),
            ]
        if self._mode in (
            InteractionMode.AWAITING_HELP_SENTENCE,
            InteractionMode.AWAITING_HINT_SENTENCE,
        ):
            return [None, None, ("Cancel", "cancel_intent")]
        return [
            ("Help me say it", "help_intent"),
            ("Give me a hint", "hint_intent"),
            ("Review", "review_intent"),
        ]

    async def _run_guarded(self, action: Callable[[], Awaitable[None]]) -> None:
        if self._waiting:
            return
        self._waiting = True
        self._input.disabled = True
        try:
            await action()
        except (httpx.HTTPError, ValueError) as exc:
            self._messages.write(f"[system] Core request failed: {exc}")
        finally:
            self._waiting = False
            self._input.disabled = False
            self._focus_input()

    # ------------------------------------------------------------------
    # Ordinary input handling (normal conversation, slash commands, and
    # answers submitted while a review item is active).
    # ------------------------------------------------------------------

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._waiting:
            self._messages.write("[system] Waiting for the current response.")
            return
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return
        self._messages.write(f"> {raw}")
        if self._mode == InteractionMode.AWAITING_HELP_SENTENCE:
            await self._run_guarded(lambda: self._run_help_capture(raw))
        elif self._mode == InteractionMode.AWAITING_HINT_SENTENCE:
            await self._run_guarded(lambda: self._run_hint_capture(raw))
        elif self._mode == InteractionMode.HELP_RESULT:
            self._messages.write("Please choose an action: Use this / Hint only / Try myself.")
        elif raw.startswith("/"):
            await self._run_guarded(lambda: self._send_command(raw))
        elif self._active_review_item_id is not None:
            await self._run_guarded(lambda: self._submit_review_answer(raw))
        else:
            await self._run_guarded(lambda: self._send_chat_message(raw))

    async def ensure_conversation(self) -> None:
        if self._conversation_id is not None:
            return
        try:
            response = await self._client.post("/v1/conversations")
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())
            self._conversation_id = str(payload["id"])
            self._messages.write(f"[system] Conversation started: {self._conversation_id}")
        except httpx.HTTPError as exc:
            self._messages.write(f"[system] Could not start conversation: {exc}")

    async def _post_command(self, raw: str) -> dict[str, Any]:
        payload: dict[str, str] = {"raw": raw}
        if self._conversation_id is not None:
            payload["conversation_id"] = self._conversation_id
        response = await self._client.post("/v1/commands/execute", json=payload)
        response.raise_for_status()
        result = cast(dict[str, Any], response.json())
        if result.get("availability") is not None:
            self._update_status(result)
        return result

    async def _send_command(self, raw: str) -> None:
        result = await self._post_command(raw)
        self._messages.write(self._format_command_result(result))
        command = result.get("command")
        if command == "review" and result.get("ok"):
            question = result.get("review_question")
            self._active_review_item_id = (
                str(question["id"]) if isinstance(question, dict) else None
            )
        elif command == "review_quit" and result.get("ok"):
            self._active_review_item_id = None

    async def _submit_review_answer(self, answer: str) -> None:
        item_id = self._active_review_item_id
        if item_id is None:
            return
        response = await self._client.post(
            f"/v1/review/{item_id}/answer",
            json={"answer": answer},
        )
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Invalid review response")
        self._messages.write(self._format_review_result(result))
        next_question = result.get("next_question")
        self._active_review_item_id = (
            str(next_question["id"]) if isinstance(next_question, dict) else None
        )

    async def _send_chat_message(self, raw: str) -> None:
        await self.ensure_conversation()
        if self._conversation_id is None:
            self._messages.write("[system] No active conversation.")
            return
        response = await self._client.post(
            f"/v1/conversations/{self._conversation_id}/messages",
            json={"content": raw},
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            self._messages.write(f"[system] {result.get('error', 'Message failed.')}")
            return
        assistant = result.get("assistant_message")
        if assistant is not None:
            self._messages.write(f"assistant: {assistant['content']}")

    async def refresh_state(self) -> dict[str, Any] | None:
        try:
            response = await self._client.get("/v1/state")
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())
            self._update_status(payload)
            return payload
        except (httpx.HTTPError, ValueError):
            self._status.update("Core: offline | Availability: unknown | Remaining: -")
            return None

    async def action_quit(self) -> None:
        if self._conversation_id is not None:
            try:
                await self._client.post(f"/v1/conversations/{self._conversation_id}/end")
            except httpx.HTTPError:
                pass
        await self._client.aclose()
        self.exit()

    def _update_status(self, payload: dict[str, Any]) -> None:
        availability_payload = payload["availability"]
        if isinstance(availability_payload, dict):
            availability = str(availability_payload["state"])
            remaining = availability_payload.get("remaining_seconds")
            expires_at = availability_payload.get("expires_at")
            llm = payload.get("llm")
        else:
            availability = str(availability_payload)
            remaining = payload.get("remaining_seconds")
            expires_at = payload.get("override_expires_at")
            llm = payload.get("llm")
        remaining_text = "-" if remaining is None else f"{remaining}s"
        if availability == "dnd" and expires_at is None:
            remaining_text = "until cleared"
        llm_text = "unknown"
        if isinstance(llm, dict):
            provider = llm.get("provider", "unknown")
            model = llm.get("model") or "-"
            status = llm.get("status", "unknown")
            llm_text = f"{provider}/{model}/{status}"
        due_review_count = payload.get("due_review_count")
        if due_review_count is not None:
            self._due_review_count = int(due_review_count)
        self._status.update(
            "Core: online"
            f" | Availability: {availability.upper()}"
            f" | Remaining: {remaining_text}"
            f" | LLM: {llm_text}"
            f" | {self._review_indicator(self._due_review_count)}"
        )

    @staticmethod
    def _review_indicator(count: int) -> str:
        if count <= 0:
            return "Review: up to date"
        if count == 1:
            return "Review: 1 item ready to review"
        return f"Review: {count} items ready to review"

    @staticmethod
    def _format_command_result(payload: dict[str, Any]) -> str:
        command = payload.get("command")
        if not payload.get("ok"):
            return f"[system] {payload.get('message', 'Command failed.')}"
        if command == "help":
            return CompanionTerminal._format_help(payload)
        if command == "hint":
            return CompanionTerminal._format_hint(payload)
        if command == "say":
            return CompanionTerminal._format_say(payload)
        if command == "review":
            question = payload.get("review_question")
            if not isinstance(question, dict):
                return "No items are due. Review complete."
            return CompanionTerminal._format_review_question(question)
        if command == "review_quit":
            return "Review stopped."
        if command == "remember":
            memory = payload.get("memory")
            if isinstance(memory, dict):
                return "Remembered: " + CompanionTerminal._format_memory(memory)
        if command == "memories":
            memories = payload.get("memories") or []
            if not memories:
                return "No memories found."
            return "Memories:\n" + "\n".join(
                f"- {CompanionTerminal._format_memory(memory)}"
                for memory in memories
                if isinstance(memory, dict)
            )
        if command == "forget":
            memory = payload.get("memory")
            if payload.get("confirmation_required") and isinstance(memory, dict):
                return (
                    f"{CompanionTerminal._format_memory(memory)}\n"
                    f"{payload.get('message')}"
                )
            return str(payload.get("message"))
        return str(payload.get("message", "Command completed."))

    @staticmethod
    def _format_help(payload: dict[str, Any]) -> str:
        lines: list[str] = []
        natural_expression = payload.get("natural_expression")
        if natural_expression:
            lines.append("Natural expression")
            lines.append(str(natural_expression))
        alternatives = payload.get("alternatives") or []
        if alternatives:
            if lines:
                lines.append("")
            lines.append("Alternative" if len(alternatives) == 1 else "Alternatives")
            lines.extend(str(alternative) for alternative in alternatives)
        notes: list[str] = []
        notes_zh = payload.get("notes_zh")
        if notes_zh:
            notes.append(str(notes_zh))
        correction = payload.get("correction")
        if correction:
            notes.append(f"Suggested correction: {correction}")
        if notes:
            if lines:
                lines.append("")
            lines.append("Note")
            lines.extend(notes)
        return "\n".join(lines) if lines else "No suggestion available."

    @staticmethod
    def _format_hint(payload: dict[str, Any]) -> str:
        hints = payload.get("hints") or []
        if not hints:
            return "No hints available."
        return "Hints\n" + "\n".join(f"- {hint}" for hint in hints)

    @staticmethod
    def _format_say(payload: dict[str, Any]) -> str:
        lines: list[str] = []
        inserted = payload.get("inserted_text")
        if inserted:
            lines.append(f"You said: {inserted}")
        assistant = payload.get("assistant_message")
        if assistant is not None:
            lines.append(f"assistant: {assistant['content']}")
        return "\n".join(lines) if lines else str(payload.get("message", "Sent."))

    @staticmethod
    def _format_review_question(question: dict[str, Any]) -> str:
        return (
            f"Review item {question.get('position', 1)}\n"
            f"{question.get('prompt')} ({question.get('kind')})"
        )

    @staticmethod
    def _format_review_result(result: dict[str, Any]) -> str:
        verdict = "Correct" if result.get("correct") else "Incorrect"
        accepted = " / ".join(str(value) for value in result.get("accepted_answers") or [])
        lines = [
            f"{verdict}. Accepted: {accepted}",
            f"Next review: {result.get('next_review_at')}",
        ]
        next_question = result.get("next_question")
        if isinstance(next_question, dict):
            lines.append(CompanionTerminal._format_review_question(next_question))
        else:
            lines.append("Complete.")
        return "\n".join(lines)

    @staticmethod
    def _format_memory(memory: dict[str, Any]) -> str:
        confidence = memory.get("confidence")
        confidence_text = "-" if confidence is None else f"{float(confidence):.2f}"
        return (
            f"{memory.get('short_id')} | {memory.get('category')} | "
            f"confidence={confidence_text} | {memory.get('content')}"
        )

    @staticmethod
    def _startup_message(payload: dict[str, Any] | None) -> str:
        if payload is None:
            return "[system] M1 UI ready. Core unavailable."
        llm = payload.get("llm")
        if not isinstance(llm, dict):
            return "[system] M1 UI ready. LLM status unavailable."
        provider = llm.get("provider", "unknown")
        model = llm.get("model") or "-"
        status = llm.get("status", "unavailable")
        return f"[system] M1 UI ready. LLM: {provider}/{model}/{status}."


async def main() -> None:
    app = CompanionTerminal()
    await app.run_async()


if __name__ == "__main__":
    asyncio.run(main())
