import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from zoneinfo import ZoneInfo

import httpx
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, RichLog, Select, Static

from companion.settings import get_settings


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
    REVIEW = "review"
    PRACTICE_PROMPT = "practice_prompt"


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
    #invitation { height: auto; border: round $accent; padding: 0 1; display: none; }
    #onboarding { height: auto; border: round $success; padding: 0 1; display: none; }
    #onboarding Select { width: 1fr; margin-right: 1; }
    #onboarding-actions { height: 3; }
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

    def __init__(self, core_url: str | None = None) -> None:
        super().__init__()
        self._core_url = (core_url or get_settings().core_url).rstrip("/")
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
        self._invitation = Static("", id="invitation")
        self._invitation_buttons = [
            Button("Start", id="invitation-start", variant="success"),
            Button("Later", id="invitation-later"),
            Button("Not today", id="invitation-dismiss"),
        ]
        self._onboarding_corrections = Select(
            [
                ("Gentle corrections — only important mistakes", "light"),
                ("Balanced corrections — helpful, without interrupting too much", "normal"),
                ("Detailed corrections — point out most mistakes", "intensive"),
            ],
            value="normal",
            id="onboarding-corrections",
        )
        self._onboarding_cadence = Select(
            [
                ("Rare reminders — give me plenty of space", "rare"),
                ("Occasional reminders — a balanced pace", "normal"),
                ("Frequent reminders — keep me practicing", "frequent"),
            ],
            value="normal",
            id="onboarding-cadence",
        )
        self._onboarding = Vertical(
            Static("Welcome! Choose how Teacher should support you (you can change this later)."),
            self._onboarding_corrections,
            self._onboarding_cadence,
            Horizontal(
                Button("Save choices", id="onboarding-save", variant="success"),
                Button("Use defaults", id="onboarding-defaults"),
                Button("Skip", id="onboarding-skip"),
                id="onboarding-actions",
            ),
            id="onboarding",
        )
        self._button_actions: dict[str, str] = {}
        self._conversation_id: str | None = None
        self._active_review_item_id: str | None = None
        self._active_review_position = 1
        self._active_review_total = 1
        self._waiting = False
        self._mode = InteractionMode.NORMAL
        self._pending_help_content: str | None = None
        self._pending_help_expression: str | None = None
        self._due_review_count = 0
        self._pending_invitation: dict[str, Any] | None = None
        self._active_practice_invitation_id: str | None = None
        self._pending_practice_completion: dict[str, str] | None = None
        self._pending_assistant_retry: dict[str, str] | None = None
        self._last_activity = time.monotonic()

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield self._status
            yield self._messages
            yield self._onboarding
            yield self._invitation
            with Horizontal(id="invitation-actions"):
                yield from self._invitation_buttons
            with Horizontal(id="actions"):
                yield from self._action_buttons
            yield self._input
        yield Footer()

    async def on_mount(self) -> None:
        self._refresh_action_buttons()
        self.set_interval(5, self.refresh_state)
        self.set_interval(
            get_settings().proactive_poll_interval_seconds,
            self.check_proactive_invitation,
        )
        self._hide_invitation()
        state = await self.refresh_state()
        await self._show_onboarding_if_needed()
        await self.ensure_conversation()
        self._messages.write(self._startup_message(state))

    # ------------------------------------------------------------------
    # Primary intents (Help me say it / Give me a hint / Review) and the
    # Use this / Hint only / Try myself follow-up to a help suggestion.
    # ------------------------------------------------------------------

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "retry_assistant":
            return self._pending_assistant_retry is not None and self._mode in (
                InteractionMode.NORMAL,
                InteractionMode.PRACTICE_PROMPT,
            )
        if action in {"help_intent", "hint_intent", "review_intent"}:
            return self._mode == InteractionMode.NORMAL
        if action == "use_suggestion":
            return (
                self._mode == InteractionMode.HELP_RESULT
                and self._pending_help_expression is not None
            )
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

    async def action_retry_assistant(self) -> None:
        if self._waiting or self._pending_assistant_retry is None:
            return
        await self._run_guarded(self._retry_assistant_reply)

    async def action_use_suggestion(self) -> None:
        if (
            self._waiting
            or self._mode != InteractionMode.HELP_RESULT
            or self._pending_help_expression is None
        ):
            return
        await self._run_guarded(self._run_use_suggestion)

    async def action_cancel_intent(self) -> None:
        if self._mode == InteractionMode.NORMAL:
            return
        if self._mode == InteractionMode.REVIEW:
            await self._run_guarded(lambda: self._send_command("/review quit"))
            return
        if self._mode == InteractionMode.PRACTICE_PROMPT:
            await self._run_guarded(self._abandon_practice)
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
        if event.button.id in {"onboarding-save", "onboarding-defaults", "onboarding-skip"}:
            await self._run_guarded(lambda: self._complete_onboarding(event.button.id or ""))
            return
        decisions = {
            "invitation-start": "start",
            "invitation-later": "snooze",
            "invitation-dismiss": "dismiss_today",
        }
        if event.button.id in decisions:
            decision = decisions[event.button.id or ""]
            await self._run_guarded(lambda: self._respond_to_invitation(decision))
            return
        action_name = self._button_actions.get(event.button.id or "")
        if action_name is None:
            return
        await self.run_action(action_name)

    async def _run_review_intent(self) -> None:
        await self._send_command("/review")

    async def _run_use_suggestion(self) -> None:
        expression = self._pending_help_expression
        assert expression is not None
        await self._send_chat_message(expression, echo_user=True)
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
        self._pending_help_expression = None
        result = await self._post_command(f"/help {raw}")
        self._messages.write(self._format_command_result(result))
        suggestion = result.get("natural_expression") or result.get("correction")
        if (
            result.get("ok")
            and result.get("command") == "help"
            and isinstance(suggestion, str)
            and suggestion.strip()
        ):
            self._pending_help_expression = suggestion.strip()
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
        if mode not in {
            InteractionMode.AWAITING_HELP_SENTENCE,
            InteractionMode.AWAITING_HINT_SENTENCE,
        }:
            raise ValueError(f"Unsupported capture mode: {mode}")
        self._mode = mode
        self._active_review_item_id = None
        self._pending_help_content = None
        self._pending_help_expression = None
        self._input.placeholder = "What do you want to say?"
        self._messages.write("What do you want to say?")
        self._after_mode_change()
        self._focus_input()

    def _reset_to_normal(self) -> None:
        self._mode = InteractionMode.NORMAL
        self._active_review_item_id = None
        self._pending_help_content = None
        self._pending_help_expression = None
        self._input.placeholder = "Say something..."
        self._after_mode_change()
        self._focus_input()

    def _enter_review(self, item_id: str, *, position: int = 1, total: int = 1) -> None:
        if not item_id:
            raise ValueError("Review item ID is required")
        self._mode = InteractionMode.REVIEW
        self._active_review_item_id = item_id
        self._active_review_position = position
        self._active_review_total = total
        self._pending_help_content = None
        self._pending_help_expression = None
        self._input.placeholder = "Answer the review question..."
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
        if self._mode == InteractionMode.REVIEW:
            return [None, None, ("Stop review", "cancel_intent")]
        if self._mode == InteractionMode.PRACTICE_PROMPT:
            if self._pending_practice_completion is not None:
                return [None, None, ("Retry completion", "cancel_intent")]
            if self._pending_assistant_retry is not None:
                return [
                    ("Retry reply", "retry_assistant"),
                    None,
                    ("Skip practice", "cancel_intent"),
                ]
            return [None, None, ("Skip practice", "cancel_intent")]
        if self._pending_assistant_retry is not None:
            return [
                ("Retry reply", "retry_assistant"),
                ("Give me a hint", "hint_intent"),
                ("Review", "review_intent"),
            ]
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
        self._last_activity = time.monotonic()
        event.input.value = ""
        if not raw:
            return
        self._messages.write(f"> {raw}")
        if raw == "/preferences" or raw.startswith("/preferences "):
            await self._run_guarded(lambda: self._handle_preferences(raw))
        elif self._mode == InteractionMode.AWAITING_HELP_SENTENCE:
            await self._run_guarded(lambda: self._run_help_capture(raw))
        elif self._mode == InteractionMode.AWAITING_HINT_SENTENCE:
            await self._run_guarded(lambda: self._run_hint_capture(raw))
        elif self._mode == InteractionMode.HELP_RESULT:
            self._messages.write("Please choose an action: Use this / Hint only / Try myself.")
        elif raw.startswith("/"):
            await self._run_guarded(lambda: self._send_command(raw))
        elif self._mode == InteractionMode.REVIEW:
            await self._run_guarded(lambda: self._submit_review_answer(raw))
        else:
            await self._run_guarded(lambda: self._send_chat_message(raw))

    async def _show_onboarding_if_needed(self) -> None:
        try:
            response = await self._client.post("/v1/preferences/onboarding/offer")
            response.raise_for_status()
            if response.json().get("should_offer"):
                self._write_onboarding()
        except (httpx.HTTPError, ValueError):
            return

    def _write_onboarding(self) -> None:
        self._messages.write(
            "Welcome! A few optional choices are ready below. Choose how much correction and "
            "how often Teacher should invite you to practice, use defaults, or skip. "
            "You can keep chatting now and change preferences later."
        )
        self._onboarding.display = True

    async def _complete_onboarding(self, action: str) -> None:
        if action == "onboarding-save":
            corrections = self._onboarding_corrections.value
            cadence = self._onboarding_cadence.value
            response = await self._client.patch(
                "/v1/preferences",
                json={"correction_style": corrections, "proactive_cadence": cadence},
            )
            confirmation = "Preferences saved."
        else:
            response = await self._client.post("/v1/preferences/reset")
            confirmation = (
                "Using default preferences."
                if action == "onboarding-defaults"
                else "Setup skipped."
            )
        response.raise_for_status()
        self._onboarding.display = False
        self._messages.write(confirmation)

    async def _handle_preferences(self, raw: str) -> None:
        parts = raw.split()
        if len(parts) == 1:
            response = await self._client.get("/v1/preferences")
        elif parts[1] in {"defaults", "skip", "reset"}:
            response = await self._client.post("/v1/preferences/reset")
        elif parts[1] == "onboard" and len(parts) == 2:
            response = await self._client.post("/v1/preferences/onboarding/restart")
            response.raise_for_status()
            if response.json().get("should_offer"):
                self._write_onboarding()
            return
        elif len(parts) == 4 and parts[1] == "set":
            key, value = parts[2], parts[3]
            payload: dict[str, object]
            if key in {"active_hours", "quiet_hours"}:
                start, separator, end = value.partition("-")
                if not separator:
                    raise ValueError("Hours must use HH:MM-HH:MM")
                payload = {f"{key}_start": start, f"{key}_end": end}
            elif key == "sound_enabled":
                if value.lower() not in {"true", "false", "on", "off"}:
                    raise ValueError("sound_enabled must be true/false or on/off")
                payload = {key: value.lower() in {"true", "on"}}
            else:
                payload = {key: value}
            response = await self._client.patch("/v1/preferences", json=payload)
        else:
            raise ValueError("Use /preferences [defaults|reset|onboard|set NAME VALUE]")
        response.raise_for_status()
        profile = cast(dict[str, Any], response.json())
        self._messages.write(
            "Preferences: "
            f"corrections={profile['correction_style']}, cadence={profile['proactive_cadence']}, "
            f"active={profile.get('active_hours_start') or '-'}–"
            f"{profile.get('active_hours_end') or '-'}, quiet="
            f"{profile.get('quiet_hours_start') or '-'}–{profile.get('quiet_hours_end') or '-'}, "
            f"practice={profile['practice_balance']}, sound={profile['sound_enabled']} "
            "(sound is saved for future audio support)."
        )

    def _can_present_invitation(self) -> bool:
        return (
            not self._waiting
            and self._mode == InteractionMode.NORMAL
            and self._active_review_item_id is None
            and self._pending_invitation is None
        )

    async def check_proactive_invitation(self) -> None:
        try:
            response = await self._client.post(
                "/v1/proactive/check",
                json={
                    "idle_seconds": max(0.0, time.monotonic() - self._last_activity),
                    "can_present": self._can_present_invitation(),
                },
            )
            response.raise_for_status()
            invitation = response.json().get("invitation")
            if isinstance(invitation, dict) and self._can_present_invitation():
                self._pending_invitation = invitation
                kind = invitation.get("kind")
                text = (
                    "A review is ready when you are."
                    if kind == "review"
                    else str(invitation.get("starter_prompt") or "Ready for a short conversation?")
                )
                self._invitation.update(f"Practice invitation\n{text}")
                self._invitation.display = True
                for button in self._invitation_buttons:
                    button.display = True
        except (httpx.HTTPError, ValueError):
            # Polling is best-effort and must never disturb an active workflow.
            return

    async def _respond_to_invitation(self, decision: str) -> None:
        invitation = self._pending_invitation
        if invitation is None:
            return
        request: dict[str, str] = {"decision": decision}
        if decision == "start" and invitation.get("kind") == "conversation":
            await self.ensure_conversation()
            if self._conversation_id is None:
                return
            request["conversation_id"] = self._conversation_id
        response = await self._client.post(
            f"/v1/proactive/invitations/{invitation['id']}/respond",
            json=request,
        )
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        self._hide_invitation()
        self._last_activity = time.monotonic()
        if decision != "start":
            self._messages.write(self._format_invitation_suppression(payload, decision))
            return
        question = payload.get("review_question")
        if isinstance(question, dict):
            self._enter_review(
                str(question["id"]),
                position=int(question.get("position", 1)),
                total=int(question.get("total", 1)),
            )
            self._messages.write(self._format_review_question(question))
        elif payload.get("review_complete"):
            self._messages.write("No items are due. Review complete.")
        elif isinstance(payload.get("conversation_starter"), str):
            self._active_practice_invitation_id = str(invitation["id"])
            self._mode = InteractionMode.PRACTICE_PROMPT
            self._messages.write(f"Practice prompt: {payload['conversation_starter']}")
            self._after_mode_change()

    def _hide_invitation(self) -> None:
        self._pending_invitation = None
        self._invitation.display = False
        for button in self._invitation_buttons:
            button.display = False

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
        if command in {"busy", "dnd", "available", "status"} and result.get("ok"):
            status = await self._fetch_proactive_status()
            if status is not None:
                self._messages.write(self._format_proactive_status(status))
        if command == "say":
            inserted = result.get("inserted_user_message")
            if (
                not result.get("ok")
                and result.get("retryable")
                and isinstance(inserted, dict)
                and self._conversation_id is not None
            ):
                self._pending_assistant_retry = {
                    "conversation_id": self._conversation_id,
                    "user_message_id": str(inserted["id"]),
                }
                self._after_mode_change()
        if command == "review" and result.get("ok"):
            question = result.get("review_question")
            if isinstance(question, dict):
                self._enter_review(
                    str(question["id"]),
                    position=int(question.get("position", 1)),
                    total=int(question.get("total", 1)),
                )
            else:
                self._reset_to_normal()
        elif command == "review_quit" and result.get("ok"):
            self._reset_to_normal()

    async def _retry_assistant_reply(self) -> None:
        evidence = self._pending_assistant_retry
        if evidence is None:
            raise ValueError("No assistant reply is pending")
        response = await self._client.post(
            "/v1/conversations/"
            f"{evidence['conversation_id']}/messages/{evidence['user_message_id']}"
            "/retry-assistant"
        )
        if response.status_code in (404, 409):
            payload = cast(dict[str, Any], response.json())
            detail = payload.get("detail", "Assistant reply can no longer be retried.")
            self._messages.write(f"[system] {detail}")
            self._pending_assistant_retry = None
            self._after_mode_change()
            return
        response.raise_for_status()
        result = cast(dict[str, Any], response.json())
        if not result.get("ok"):
            self._messages.write(
                f"[system] Assistant reply failed: {result.get('error', 'Retry failed.')}"
            )
            return
        assistant = result.get("assistant_message")
        if not isinstance(assistant, dict):
            raise ValueError("Invalid assistant retry response")
        self._messages.write(f"assistant: {assistant['content']}")
        self._pending_assistant_retry = None
        self._after_mode_change()
        invitation_id = evidence.get("invitation_id")
        if invitation_id is not None:
            self._pending_practice_completion = {
                "invitation_id": invitation_id,
                "conversation_id": evidence["conversation_id"],
                "user_message_id": evidence["user_message_id"],
                "assistant_message_id": str(assistant["id"]),
            }
            await self._finalize_practice()

    async def _submit_review_answer(self, answer: str) -> None:
        item_id = self._active_review_item_id
        if self._mode != InteractionMode.REVIEW or item_id is None:
            return
        response = await self._client.post(
            f"/v1/review/{item_id}/answer",
            json={
                "answer": answer,
                "position": self._active_review_position,
                "total": self._active_review_total,
            },
        )
        response.raise_for_status()
        payload = cast(dict[str, Any], response.json())
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Invalid review response")
        self._messages.write(self._format_review_result(result))
        next_question = result.get("next_question")
        if isinstance(next_question, dict):
            self._enter_review(
                str(next_question["id"]),
                position=int(next_question.get("position", 1)),
                total=int(next_question.get("total", 1)),
            )
        else:
            self._reset_to_normal()

    async def _send_chat_message(self, raw: str, *, echo_user: bool = False) -> None:
        if self._pending_practice_completion is not None:
            await self._finalize_practice()
            return
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
            user_message = result.get("user_message")
            if result.get("retryable") and isinstance(user_message, dict):
                self._pending_assistant_retry = {
                    "conversation_id": self._conversation_id,
                    "user_message_id": str(user_message["id"]),
                }
                if self._mode == InteractionMode.PRACTICE_PROMPT:
                    invitation_id = self._active_practice_invitation_id
                    if invitation_id is None:
                        raise ValueError("Invalid practice retry state")
                    self._pending_assistant_retry["invitation_id"] = invitation_id
                self._messages.write(
                    "[system] Your message was saved, but the assistant reply failed: "
                    f"{result.get('error', 'Message failed.')} Choose Retry reply."
                )
                self._after_mode_change()
                return
            self._messages.write(f"[system] {result.get('error', 'Message failed.')}")
            return
        if echo_user:
            self._messages.write(f"You said: {raw}")
        assistant = result.get("assistant_message")
        if assistant is not None:
            self._messages.write(f"assistant: {assistant['content']}")
        if self._mode == InteractionMode.PRACTICE_PROMPT:
            invitation_id = self._active_practice_invitation_id
            user_message = result.get("user_message")
            if (
                invitation_id is None
                or not isinstance(user_message, dict)
                or not isinstance(assistant, dict)
            ):
                raise ValueError("Invalid practice message response")
            self._pending_practice_completion = {
                "invitation_id": invitation_id,
                "conversation_id": self._conversation_id,
                "user_message_id": str(user_message["id"]),
                "assistant_message_id": str(assistant["id"]),
            }
            self._input.placeholder = "Practice sent — retry completion if needed..."
            self._after_mode_change()
            await self._finalize_practice()

    async def _finalize_practice(self) -> None:
        evidence = self._pending_practice_completion
        if evidence is None:
            raise ValueError("No practice completion is pending")
        completion = await self._client.post(
            f"/v1/proactive/invitations/{evidence['invitation_id']}/practice/complete",
            json={
                "conversation_id": evidence["conversation_id"],
                "user_message_id": evidence["user_message_id"],
                "assistant_message_id": evidence["assistant_message_id"],
            },
        )
        completion.raise_for_status()
        outcome = completion.json().get("outcome")
        if outcome == "learning_signal_captured":
            self._messages.write("Practice complete. A useful learning point was saved for review.")
        else:
            self._messages.write("Practice complete. This conversation was not graded.")
        self._pending_practice_completion = None
        self._active_practice_invitation_id = None
        self._reset_to_normal()

    async def _abandon_practice(self) -> None:
        if self._pending_practice_completion is not None:
            await self._finalize_practice()
            return
        invitation_id = self._active_practice_invitation_id
        if invitation_id is None:
            raise ValueError("No active practice invitation")
        response = await self._client.post(
            f"/v1/proactive/invitations/{invitation_id}/practice/abandon"
        )
        response.raise_for_status()
        self._active_practice_invitation_id = None
        self._reset_to_normal()
        self._messages.write("Practice skipped.")

    async def refresh_state(self) -> dict[str, Any] | None:
        try:
            response = await self._client.get("/v1/state")
            response.raise_for_status()
            payload = cast(dict[str, Any], response.json())
            proactive = await self._fetch_proactive_status()
            if proactive is not None:
                payload["proactive"] = proactive
            self._update_status(payload)
            return payload
        except (httpx.HTTPError, ValueError):
            self._status.update("Core: offline | Availability: unknown | Remaining: -")
            return None

    async def _fetch_proactive_status(self) -> dict[str, Any] | None:
        try:
            response = await self._client.post(
                "/v1/proactive/status",
                json={
                    "idle_seconds": max(0.0, time.monotonic() - self._last_activity),
                    "can_present": self._can_present_invitation(),
                },
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except (httpx.HTTPError, ValueError):
            return None

    @staticmethod
    def _format_proactive_status(status: dict[str, Any]) -> str:
        cadence = (
            "Runtime default"
            if status.get("uses_legacy_policy") is True
            else str(status.get("cadence", "normal")).title()
        )
        due = int(status.get("due_review_count", 0))
        reason = str(status.get("reason", ""))
        boundary = status.get("not_before") or status.get("availability_expires_at")
        when = CompanionTerminal._format_proactive_time(boundary)
        messages = {
            "busy": f"Busy until {when} — no practice invitations.",
            "dnd": "DND — proactive paused until you switch back to Available.",
            "outside_active_hours": "Outside active hours — proactive paused.",
            "quiet_hours": "Quiet hours — proactive paused.",
            "accepted_practice": "Practice is already active — no new invitation.",
            "pending_invitation": "A practice invitation is waiting for your response.",
            "snoozed": f"Later — not before {when}.",
            "dismissed_today": f"No more invitations today — paused until {when}.",
            "accepted_cooldown": f"Practice cooldown — not before {when}.",
            "daily_limit": "No more invitations today.",
            "ui_cannot_present": "Teacher won't interrupt the current activity.",
        }
        if reason == "insufficient_idle":
            minutes = max(1, round(float(status.get("idle_threshold_seconds", 0)) / 60))
            detail = f"May invite after about {minutes} minutes of inactivity."
        elif reason in messages:
            detail = messages[reason]
        elif due:
            detail = f"{due} review{'s' if due != 1 else ''} due — next invite prioritizes review."
        else:
            detail = "Available — no reviews due; next invite may be conversation practice."
        return f"Proactive: {cadence} · {detail}"

    @staticmethod
    def _format_proactive_time(value: object) -> str:
        if not isinstance(value, str):
            return "later"
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(ZoneInfo(get_settings().timezone)).strftime("%H:%M")

    @staticmethod
    def _format_invitation_suppression(payload: dict[str, Any], decision: str) -> str:
        invitation = payload.get("invitation")
        boundary = invitation.get("suppress_until") if isinstance(invitation, dict) else None
        when = CompanionTerminal._format_proactive_time(boundary)
        if decision == "snooze":
            return f"Okay — I won't ask again before {when}."
        return f"Got it — no more proactive practice invitations today (until {when})."

    async def action_quit(self) -> None:
        if self._active_practice_invitation_id is not None:
            try:
                if self._pending_practice_completion is not None:
                    await self._finalize_practice()
                else:
                    await self._abandon_practice()
                if self._active_practice_invitation_id is not None:
                    raise ValueError("Practice did not reach a terminal state")
                self._pending_assistant_retry = None
            except (httpx.HTTPError, ValueError) as exc:
                self._messages.write(
                    f"[system] Could not resolve active practice; quit cancelled: {exc}"
                )
                return
        if self._conversation_id is not None:
            try:
                response = await self._client.post(f"/v1/conversations/{self._conversation_id}/end")
                response.raise_for_status()
                payload = response.json()
                extraction = payload.get("memory_extraction")
                if isinstance(extraction, dict) and extraction.get("retryable"):
                    self._messages.write(
                        "[system] Memory extraction failed. Quit again to retry safely."
                    )
                    return
            except httpx.HTTPError as exc:
                self._messages.write(f"[system] Could not end conversation; quit cancelled: {exc}")
                return
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
        proactive = payload.get("proactive")
        proactive_text = (
            f" | {self._format_proactive_status(proactive)}" if isinstance(proactive, dict) else ""
        )
        self._status.update(
            "Core: online"
            f" | Availability: {availability.upper()}"
            f" | Remaining: {remaining_text}"
            f" | LLM: {llm_text}"
            f" | {self._review_indicator(self._due_review_count)}"
            f"{proactive_text}"
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
        if command == "say" and payload.get("inserted_into_conversation"):
            return CompanionTerminal._format_say(payload)
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
                return f"{CompanionTerminal._format_memory(memory)}\n{payload.get('message')}"
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
        assistant_error = payload.get("assistant_error")
        if assistant_error:
            lines.append(f"[system] Assistant reply failed: {assistant_error}")
        return "\n".join(lines) if lines else str(payload.get("message", "Sent."))

    @staticmethod
    def _format_review_question(question: dict[str, Any]) -> str:
        return (
            f"Review item {question.get('position', 1)} of {question.get('total', 1)} "
            f"({question.get('remaining', 1)} remaining)\n"
            f"{question.get('prompt')} ({question.get('kind')})"
        )

    @staticmethod
    def _format_review_result(result: dict[str, Any]) -> str:
        verdict = "Correct" if result.get("correct") else "Incorrect"
        accepted = " / ".join(str(value) for value in result.get("accepted_answers") or [])
        lines = [
            f"{verdict}.",
            f"Prompt: {result.get('prompt')}",
            f"Your answer: {result.get('submitted_answer')}",
            f"Accepted answer(s): {accepted}",
            f"Next review: {CompanionTerminal._format_review_time(result.get('next_review_at'))}",
        ]
        next_question = result.get("next_question")
        if isinstance(next_question, dict):
            lines.append(CompanionTerminal._format_review_question(next_question))
        else:
            lines.append("Complete.")
        return "\n".join(lines)

    @staticmethod
    def _format_review_time(value: object) -> str:
        if not isinstance(value, str):
            return "scheduled"
        try:
            review_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        if review_at.tzinfo is None:
            review_at = review_at.replace(tzinfo=UTC)
        timezone_name = get_settings().timezone
        local_review_at = review_at.astimezone(ZoneInfo(timezone_name))
        return local_review_at.strftime(f"%a, %b %-d at %-I:%M %p {timezone_name}")

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
            return "[system] Companion UI ready. Core unavailable."
        llm = payload.get("llm")
        if not isinstance(llm, dict):
            return "[system] Companion UI ready. LLM status unavailable."
        provider = llm.get("provider", "unknown")
        model = llm.get("model") or "-"
        status = llm.get("status", "unavailable")
        return f"[system] Companion UI ready. LLM: {provider}/{model}/{status}."


async def main() -> None:
    app = CompanionTerminal()
    await app.run_async()


def run() -> None:
    """Run the installed terminal UI console entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
