## Why

Teacher can already capture difficult expressions and schedule reviews, but the user must remember
to open `/review` manually. M4 should make the companion feel proactive while it is running without
interrupting busy or do-not-disturb periods, repeatedly nagging, or requiring background macOS
services.

## What Changes

- Add a deterministic Core-owned scheduler that decides when an in-app practice invitation is
  eligible while the terminal UI is connected.
- Prioritize an invitation to review when learning items are due; otherwise offer a lightweight
  English conversation practice after an eligible idle interval.
- Suppress invitations while availability is `busy` or `dnd`, during an active review, while an
  invitation is already pending, and while cooldown or same-day dismissal rules apply.
- Let the user accept, snooze, or dismiss an invitation for the rest of the local day. Persist those
  decisions so restarting the app does not immediately repeat an invitation.
- Keep scheduling, invitation state, and starter selection deterministic in Core. Polling in the UI
  must not call Groq, and accepting a review invitation reuses the existing local review flow.
- Display invitations as explicit, non-message UI cards with natural actions instead of introducing
  new slash commands.
- Add migration, API schemas, Core tests, terminal interaction tests, and M4 documentation.
- Exclude macOS system notifications, launch-at-login/background processes, voice, hardware, and
  proactive messages while the terminal UI is closed.

Measurable outcome: with Teacher open and availability set to `available`, an eligible user receives
at most one pending invitation, can start the appropriate practice flow in one action, and can
snooze or dismiss it without another invitation appearing before the recorded boundary.

## Capabilities

### New Capabilities

- `proactive-practice`: Eligibility, prioritization, suppression, persisted user decisions, API
  behavior, and terminal presentation for in-app proactive practice invitations.

### Modified Capabilities

- None.

## Impact

- Core: a new proactive domain/service and repository, clock-driven scheduling policy, API routes,
  and integration with availability and learning queries.
- Persistence: one Alembic migration for invitation decisions and delivery state.
- Terminal UI: periodic Core polling plus invitation cards and accept/snooze/dismiss actions.
- Tests and documentation: deterministic fake-clock coverage, HTTP/UI integration coverage, and M4
  operating documentation.
- External dependencies: none; no new LLM, scheduler framework, or macOS background service.
