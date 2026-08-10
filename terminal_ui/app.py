import asyncio
from typing import Any, cast

import httpx
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static


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
    #command {
        dock: bottom;
    }
    """

    def __init__(self, core_url: str = "http://127.0.0.1:8000") -> None:
        super().__init__()
        self._core_url = core_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._core_url, timeout=40.0)
        self._status = Static(
            "Core: unknown | Availability: unknown | Remaining: - | LLM: unknown",
            id="status",
        )
        self._messages = RichLog(id="messages", wrap=True, markup=False)
        self._input = Input(
            placeholder="Type English or use /help, /remember, /memories, /forget",
            id="command",
        )
        self._conversation_id: str | None = None
        self._waiting = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield self._status
            yield self._messages
            yield self._input
        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(5, self.refresh_state)
        state = await self.refresh_state()
        await self.ensure_conversation()
        self._messages.write(self._startup_message(state))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._waiting:
            self._messages.write("[system] Waiting for the current response.")
            return
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return
        self._messages.write(f"> {raw}")
        self._waiting = True
        self._input.disabled = True
        try:
            if raw.startswith("/"):
                await self._send_command(raw)
            else:
                await self._send_chat_message(raw)
        except (httpx.HTTPError, ValueError) as exc:
            self._messages.write(f"[system] Core request failed: {exc}")
        finally:
            self._waiting = False
            self._input.disabled = False
            self._input.focus()

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

    async def _send_command(self, raw: str) -> None:
        payload: dict[str, str] = {"raw": raw}
        if self._conversation_id is not None:
            payload["conversation_id"] = self._conversation_id
        response = await self._client.post("/v1/commands/execute", json=payload)
        response.raise_for_status()
        result = response.json()
        self._messages.write(self._format_command_result(result))
        if result.get("availability") is not None:
            self._update_status(result)

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
        self._status.update(
            "Core: online"
            f" | Availability: {availability.upper()}"
            f" | Remaining: {remaining_text}"
            f" | LLM: {llm_text}"
        )

    @staticmethod
    def _format_command_result(payload: dict[str, Any]) -> str:
        command = payload.get("command")
        if not payload.get("ok"):
            return f"[system] {payload.get('message', 'Command failed.')}"
        if command == "help":
            lines: list[str] = []
            natural_expression = payload.get("natural_expression")
            if natural_expression:
                lines.append(f"[help] {natural_expression}")
            alternatives = payload.get("alternatives") or []
            if alternatives:
                lines.append("[help alt] " + ", ".join(alternatives))
            notes_zh = payload.get("notes_zh")
            if notes_zh:
                lines.append(f"[help zh] {notes_zh}")
            correction = payload.get("correction")
            if correction:
                lines.append(f"[help correction] {correction}")
            return "\n".join(lines)
        if command == "hint":
            hints = payload.get("hints") or []
            return "[hint]\n" + "\n".join(f"- {hint}" for hint in hints)
        if command == "say":
            lines = [f"[say] inserted: {payload.get('inserted_text')}"]
            assistant = payload.get("assistant_message")
            if assistant is not None:
                lines.append(f"assistant: {assistant['content']}")
            return "\n".join(lines)
        if command == "remember":
            memory = payload.get("memory")
            if isinstance(memory, dict):
                return "[memory] " + CompanionTerminal._format_memory(memory)
        if command == "memories":
            memories = payload.get("memories") or []
            if not memories:
                return "[memories] No memories found."
            return "[memories]\n" + "\n".join(
                f"- {CompanionTerminal._format_memory(memory)}"
                for memory in memories
                if isinstance(memory, dict)
            )
        if command == "forget":
            memory = payload.get("memory")
            if payload.get("confirmation_required") and isinstance(memory, dict):
                return (
                    f"[forget] {CompanionTerminal._format_memory(memory)}\n"
                    f"[system] {payload.get('message')}"
                )
            return f"[forget] {payload.get('message')}"
        return str(payload.get("message", "Command completed."))

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
