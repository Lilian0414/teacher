# Change: Simplify learning interactions and remove command-heavy UX

## Why

The M3 terminal exposes internal command names (`/help`, `/hint`, `/say`) and implementation
labels (`[help]`, `[help alt]`, `[help zh]`, `[help correction]`, `[say] inserted`) directly to the
user. A first-time user must learn the difference between commands representing user intent rather
than concepts they should need to memorize, and the output reads like debugging logs rather than a
learning product.

## What Changes

- Add three intent-based entry points to the terminal UI — Help me say it, Give me a hint, Review —
  reachable through on-screen buttons and keyboard shortcuts (Ctrl+H, Ctrl+G, Ctrl+R), so a new user
  never needs to type a slash command.
- Keep `/help`, `/hint`, `/say`, `/review`, and the M2 memory commands available as an advanced
  slash-command interface with unchanged backend semantics.
- Replace debug-style command-result rendering with structured, readable output (e.g. "Natural
  expression" / "Alternative" / "Note" instead of `[help]` / `[help alt]` / `[help zh]`).
- Add a "Help me say it" follow-up step (Use this / Hint only / Try myself) that reuses the existing
  `/say` and `/hint` command paths instead of duplicating their logic.
- Expose the number of due review items in the status bar via a small, additive `/v1/state` field
  (`due_review_count`) so review availability is visible without starting `/review`.
- Replace the overloaded command-list input placeholder with a simple "Say something..." prompt.

## Non-goals

- No M4 proactive behavior: no proactive invitations, background reminders, or push/OS
  notifications.
- No voice, webcam, or hardware integration.
- No change to spaced-repetition scheduling, answer grading, or learning-item deduplication.
- No large backend rewrite; the API addition is limited to a single read-only count on `/v1/state`.

## Measurable Outcome

A new user can complete a full help → use-this → review loop using only on-screen buttons or
keyboard shortcuts, without typing a slash command. Existing slash commands and their JSON
contracts are unchanged (except for the additive `due_review_count` field on `/v1/state`). Ruff,
mypy, and the full pytest suite remain green.

## Capabilities

### New Capabilities

- `terminal-ui`: Intent-based interaction entry points, the help/hint/review flow state machine,
  and structured (non-debug) presentation of command results.

### Modified Capabilities

- `learning-loop`: Adds a due-review count accessor so due items are discoverable without starting
  an interactive review session.

## Impact

- Adds `LearningRepository.due_count` / `LearningService.due_count` and a `due_review_count` field
  on `StateResponse`.
- Rewrites `terminal_ui/app.py` presentation and interaction handling; no changes to
  `commands/parser.py` or `api/routes.py` command dispatch logic.
- Extends unit tests for the terminal UI and adds one integration test for the due-count field.
- Adds no new runtime dependency.
