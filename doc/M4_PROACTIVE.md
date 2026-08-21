# M4: In-app proactive practice

M4 lets the running Textual app offer low-pressure review or conversation practice. Core owns all
eligibility, availability suppression, time-zone boundaries, cooldowns, daily limits, persisted
decisions, and deterministic conversation starters. Review is prioritized when an item is due.

The UI polls `POST /v1/proactive/check` every 30 seconds and sends only its idle duration and whether
it can safely present a card. The card offers **Start**, **Later**, and **Not today**. Starting review
reuses `LearningService.first_due()` and does not create an attempt until an answer is submitted.
Starting conversation displays a local prompt; only the user's later response enters normal chat and
may invoke the configured provider. Polling and acceptance never invoke an LLM.

## Configuration and demo

Defaults are 10 minutes idle for review, 30 minutes for conversation, 30 minutes for snooze, a
60-minute post-accept cooldown, and three deliveries per configured local day. For a quick demo:

```bash
COMPANION_PROACTIVE_REVIEW_IDLE_SECONDS=5 \
COMPANION_PROACTIVE_CONVERSATION_IDLE_SECONDS=10 \
COMPANION_PROACTIVE_POLL_INTERVAL_SECONDS=5 python -m terminal_ui.app
```

Upgrade first with `alembic upgrade head`. Roll back M4 only with
`alembic downgrade 20260810_0004` after stopping the updated UI.

## Explicit exclusions

Invitations exist only while the terminal UI is open. M4 does not add macOS notifications,
closed-app behavior, launch agents, menu-bar/background processes, voice, hardware, or dependencies.
