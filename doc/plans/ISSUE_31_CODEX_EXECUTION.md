# Issue #31 Codex execution contract

Source: GitHub Issue #31 — Close the proactive conversation practice outcome loop.

Base: `main` after Issue #30 reached `main` and post-merge CI passed.

## Goal

Turn an accepted proactive **conversation** invitation into one bounded, identifiable practice interaction with a durable, truthful outcome. Reuse the ordinary-conversation learning signal/provenance path from Issue #29; do not create a second mastery, grading, or scheduling system.

## Verified current behavior

- `ProactiveService.check()` chooses `review` when due learning items exist and `conversation` otherwise.
- `respond(..., START)` immediately resolves a pending invitation to `accepted`, sets the existing accept cooldown, and returns either the real review question or a static conversation starter.
- For a conversation invitation, the terminal UI enters `InteractionMode.PRACTICE_PROMPT`.
- The next user input is sent through the ordinary conversation message endpoint, then the UI immediately resets to normal.
- Ordinary conversation already performs Issue #29 post-reply learning-signal extraction and can persist a `LearningOccurrence`/`LearningItem`.
- Nothing currently links that practice turn back to the proactive invitation, records completion/non-evaluation, or records abandonment if the user skips after starting.
- Snooze and dismiss are already persistent pending-invitation decisions and should remain authoritative.
- The review invitation branch already reuses `LearningService.first_due()` and must not be redesigned.

## Required behavior

1. **Represent a bounded proactive conversation practice lifecycle**
   - Preserve `pending -> accepted` for START if that is the least disruptive representation, but add explicit terminal semantics for a started conversation practice: completed and abandoned (names may vary if the model is clearer).
   - A conversation invitation must not remain permanently `accepted` after the one bounded practice turn or after an explicit Skip practice action.
   - Repeated completion/abandon requests must be safe and deterministic; conflicting terminal transitions must not overwrite each other silently.

2. **Link the practice turn to real conversation evidence**
   - Persist durable linkage from the invitation to the actual conversation turn used for practice: at minimum the conversation, user-message, and assistant-message identities (or an equivalent validated source reference).
   - Validate that supplied source identifiers refer to the expected roles/conversation/current user before persisting the link; do not trust arbitrary client-provided message IDs.
   - Prefer additive columns on the existing invitation row unless a separate small practice-outcome table is clearly cleaner. Add a reversible Alembic migration if persistence fields/statuses require schema changes.

3. **Reuse Issue #29 rather than re-extracting learning**
   - The practice response must still travel through the existing ordinary `ConversationService.send_user_message()` path so successful assistant delivery and Issue #29 learning extraction semantics remain unchanged.
   - Do **not** call a second learning-signal LLM extraction for proactive practice.
   - After the successful ordinary turn, derive the proactive outcome from Issue #29 provenance: if that user message produced a `LearningOccurrence`, record a bounded outcome such as `learning_signal_captured` and link/read the existing learning item/occurrence as needed; otherwise record a truthful `completed_not_evaluated` (or equivalent) outcome.
   - An Issue #29 extraction failure/no candidate must not turn a successful chat reply into a failed practice turn and must not be reported as an incorrect learner answer.

4. **Keep completion retry-safe without duplicating chat**
   - Prefer a flow where the UI sends the ordinary chat turn once, receives its real message IDs, then finalizes the invitation through an idempotent Core endpoint/service call. Retrying invitation finalization must not resend or duplicate the chat turn.
   - If another architecture is chosen, provide equivalent proof that transport retry cannot create duplicate practice messages/outcomes.

5. **Persist abandonment honestly**
   - When the user chooses `Skip practice` after START, persist an abandoned/skipped terminal outcome instead of merely resetting the UI.
   - Abandonment is not an incorrect learning attempt and must not create/reset a `LearningItem`.
   - Existing pre-start `snooze` and `dismiss_today` behavior remains unchanged and tested.

6. **Close the future-behavior loop using existing readers**
   - If the practice turn creates an Issue #29 learning item, the existing due-learning source of truth must make that item visible to review/context and therefore allow a later proactive check (after suppression/cooldown) to choose `review` because due work exists.
   - Do not add a second proactive score/mastery field to force this transition.
   - If no learning signal is created, preserve the completion record and existing cooldown/suppression semantics; the UI must not claim the turn was graded.

7. **UI/API truthfulness**
   - Keep the active invitation ID while in conversation practice mode so the next chat result can be finalized against the correct invitation.
   - After completion, show a concise truthful outcome: for example that a useful learning point was saved for review, or that the short conversation is complete but was not graded.
   - After Skip practice, show a concise skipped/abandoned state.
   - Do not expose internal prompts/provider payloads.
   - Polling `/proactive/check` remains best-effort and must not issue an LLM request merely because a timer fired.

## Acceptance tests

Add deterministic coverage proving at least:

- conversation invitation -> START creates a bounded active practice state and returns the existing starter;
- one real ordinary conversation turn can be linked back to that invitation and moves it to a terminal completed state;
- when that turn produces an Issue #29 occurrence/item, the proactive outcome records that existing learning signal rather than creating a second one;
- after cooldown/suppression, the same existing due item causes a future proactive check to select `review`;
- when the turn produces no Issue #29 candidate (or extraction fails after a successful reply), practice still completes truthfully as non-evaluated and no incorrect attempt/state mutation is manufactured;
- retrying completion is idempotent and does not duplicate conversation messages, learning occurrences, or invitation outcomes;
- invalid/unrelated conversation/message IDs cannot be attached to an invitation;
- START then Skip practice persists abandonment and creates no learning attempt/item solely because of the skip;
- snooze and dismiss-before-start remain persistent and retain their current suppression semantics;
- duplicate/conflicting decisions/transitions remain 409 or an equally explicit deterministic conflict;
- the existing proactive review path still starts real review and remains covered;
- terminal UI tests prove practice completion/skip does not silently reset without Core state update.

## Likely touch points (not a required file list)

- `src/companion/proactive/service.py`
- `src/companion/proactive/repository.py`
- `src/companion/proactive/schemas.py`
- `src/companion/persistence/models.py`
- `src/companion/api/routes.py` / dependency wiring
- a narrow read of Issue #29 `LearningOccurrence` provenance via existing learning repository/service
- `src/terminal_ui/app.py`
- `tests/integration/test_m4_proactive.py`
- focused terminal UI/unit tests
- reversible migration if persistence changes are required

Prefer the smallest design that keeps one learning source of truth.

## Explicit non-goals

- No new mastery model, grading model, spaced-repetition algorithm, or learning-item identity.
- No second learning-signal extraction pipeline.
- No LLM judge for conversation practice.
- No proactive recommendation model or event bus.
- No broad agent framework/LangGraph.
- No memory-retrieval work (#33).
- No `/say` reliability work (#34).
- No personality/Japanese/provider redesign.
- Do not redesign the existing review flow.

## Required verification

Run and report the strongest applicable repository gates:

- `ruff check .`
- strict `mypy`
- `pytest`
- focused proactive integration/UI tests
- `git diff --check`
- SQLite Alembic upgrade/downgrade round trip if a migration is added

If a layer cannot run, report that exact limitation rather than claiming it passed.

## Delivery / duplicate-run guard

- Use one active Codex implementation task by default.
- Production implementation should be on a dedicated child branch from `spec/issue-31-proactive-conversation-outcome` and target that planning branch when publication controls are available.
- Do not merge. ChatGPT owns complete diff review, CI verification, and merge.
- If publication is blocked, preserve the same completed task/commit and use its Push/Create PR handoff later; do not reimplement merely because publishing failed.
- Do not broaden into #33/#34 or unrelated cleanup.
