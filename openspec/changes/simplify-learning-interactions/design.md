## Context

M3 (`learning-loop`) implemented `/help`, `/hint`, `/say`, and `/review` as slash commands with
debug-style terminal rendering. M3.5 is a UI/interaction cleanup: it must not change the
deterministic command semantics, learning-item deduplication, or review scheduling already
specified and tested in `learning-loop`. See `proposal.md` for motivation.

## Goals / Non-Goals

**Goals:**

- Make Help me say it / Give me a hint / Review reachable without typing a slash command.
- Reuse the existing `/help`, `/hint`, and `/say` command execution path for the new entry points
  instead of adding parallel backend logic.
- Remove implementation-oriented labels from user-facing output.
- Surface due-review availability passively, without a proactive notification.

**Non-Goals:**

- Changing what counts as a reviewable answer, how items are scheduled, or how learning items are
  deduplicated (all already specified under `learning-loop`).
- Adding proactive reminders or background notifications (M4 scope).
- A full mouse-only or keyboard-only interface; both are supported since Textual actions can be
  triggered from either a bound key or a button press.

## Decisions

### A small terminal-side interaction state machine, not new backend endpoints

The terminal now tracks an `InteractionMode` (`normal`, `awaiting_help_sentence`,
`awaiting_hint_sentence`, `help_result`). Entering "Help me say it" or "Give me a hint" asks for a
sentence, then posts to the existing `/v1/commands/execute` endpoint with `/help <content>` or
`/hint <content>` exactly as the slash command would. A successful `/help` result moves the
terminal into `help_result` mode, which offers Use this / Hint only / Try myself; those, in turn,
dispatch to the existing `/say` and `/hint` paths using the sentence captured earlier.

Alternative considered: add a new `/v1/intents/*` API surface. Rejected because it would duplicate
business logic already covered by `commands/execute`, doubling the surface that must stay
consistent with `learning-loop`'s deterministic behavior.

### Reuse the same three buttons for both the primary intents and the help follow-up

Rather than adding a second row of widgets, the three action buttons are relabeled based on
`InteractionMode`: Help me say it / Give me a hint / Review in `normal` mode, and Use this / Hint
only / Try myself in `help_result` mode. Keyboard bindings are exposed the same way via Textual's
`check_action`, which Textual's `Footer` widget uses to show or hide a binding depending on
context.

Alternative considered: a fixed six-button layout. Rejected as unnecessary complexity for a
terminal-width-constrained UI, and it would make the "only one primary action available at a time"
invariant harder to see at a glance.

### Deviate from the example Ctrl+I hint binding

The issue's example keys are Ctrl+H / Ctrl+I / Ctrl+R. Ctrl+I is used because most terminals report
it identically to the Tab key at the byte level, so binding it would silently break Tab-based focus
navigation for anyone whose terminal cannot distinguish the two. Ctrl+G is used for the hint intent
instead; the issue explicitly allows the exact widgets/keys to be flexible.

### Add one additive, read-only field instead of a new endpoint for the due-review indicator

`due_review_count` is added to the existing `/v1/state` response (already polled every 5 seconds by
the terminal) rather than introducing a new endpoint. The count is computed by a new
`LearningService.due_count()` that mirrors the existing `first_due()` query but returns a count
instead of the first item, so it shares the same due-time semantics as `/review`.

Alternative considered: derive the count client-side by calling `/v1/review` speculatively.
Rejected because that would silently create review-session side effects on every poll and
duplicate query logic that belongs in the learning service.

## Risks / Trade-offs

- [Existing terminal-UI unit tests assert the old debug-style strings] → These are the exact
  strings the issue asks to remove; the tests are rewritten in this change to assert the new
  structured format instead of the old bracketed one.
- [Keyboard shortcuts vary by terminal emulator] → Textual's `check_action` hides bindings that
  don't apply to the current mode, so an unavailable shortcut is not shown as active; buttons remain
  a fully equivalent, discoverable alternative.
- [Relabeling the same three buttons could confuse a user mid-flow] → The status/messages log
  always announces the mode transition in plain text ("What do you want to say?", "Actions: ...")
  alongside the button relabel.

## Migration Plan

1. Purely additive on the backend (`due_review_count` defaults to `0` and existing consumers of
   `StateResponse` that ignore unknown fields are unaffected).
2. No database migration; `due_count` reads the same `learning_items` table `first_due` already
   queries.
3. Rollback is a plain revert; no persisted state format changes.
