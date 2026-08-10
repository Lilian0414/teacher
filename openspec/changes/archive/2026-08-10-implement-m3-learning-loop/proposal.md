## Why

The companion can already help with English expressions, but that help disappears after the
command response and cannot become deliberate practice. M3 turns existing `/help` and `/hint`
usage into a small, persistent learning loop so previously difficult expressions can reappear at
the right time and shape later conversation practice.

## What Changes

- Persist deduplicated learning items and their review attempts in SQLite.
- Make successful `/help` and `/hint` commands create or update an expression learning item
  without writing their examples to long-term life memory.
- Add deterministic `/review` behavior that starts a resumable, one-question-at-a-time session
  over due items, evaluates each submitted answer, records the result, and advances a simple
  spaced-review date without relying on real waiting time in tests.
- Add learning context for normal conversation so due learning goals can be combined with a
  small relevant set of active life memories when generating an opening or reply topic.
- Expose enough structured command data for the terminal UI to enter, advance, and leave an
  interactive review session while preserving the existing Core-through-HTTP boundary.
- Document and test the completed M3 behavior.
- Keep active reminders, background scheduling, proactive invitations, voice, hardware,
  screen monitoring, and file tools out of scope.

Measurable outcome: an expression requested through `/help` or `/hint` is stored once, remains
available after restart, appears when due through `/review`, receives a deterministic next-review
date after an attempt, and can influence a conversation together with relevant active memory.

## Capabilities

### New Capabilities

- `learning-loop`: Persistent expression learning items, review attempts and dates, interactive
  `/review` sessions, and conversation context informed by due learning goals plus eligible life
  memory.

### Modified Capabilities

None.

## Impact

- Adds an Alembic migration and SQLAlchemy models for learning items and attempts.
- Adds learning schemas, repository, service, context builder, and dependency wiring.
- Extends deterministic command parsing, command execution responses, conversation context, and
  terminal UI rendering.
- Extends fake-provider unit and integration coverage; ordinary validation continues to make no
  real Groq requests.
- Adds no new runtime dependency and does not change M0 availability or M2 memory semantics.
