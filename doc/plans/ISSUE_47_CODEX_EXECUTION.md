# Issue #47 Codex execution contract

Source: GitHub Issue #47 — Keep `/say` out of ordinary-conversation learning signals.

Base: `main` at `a26375717d9f7626715806e9f4748eb8c1a00619` after Issue #34 reached main and post-merge CI passed.

## Goal

Fix the final E2E regression where `/say` is currently able to create Issue #29 ordinary-conversation learning signals because its translated user turn delegates to `ConversationService.send_user_message()`.

Preserve one assistant-generation/persistence implementation and make learning-signal eligibility explicit and durable enough that Issue #34 assistant-only retry also respects the `/say` exclusion.

## Verified current behavior

- `ConversationService.send_user_message()` persists a user message with `source="terminal"`, calls `_reply_to_user_message()`, and after a successful assistant reply performs best-effort `extract_learning_signal()` + `LearningService.capture_conversation_signal()`.
- `insert_translated_user_message()` simply calls `send_user_message()` with translated English.
- Production `get_conversation_service()` injects `learning_service`, so `/say` is eligible for #29 extraction in real runtime.
- The README states `/help` and `/hint` create learning items and `/say` never does.
- Existing M1/M3 `/say` tests miss the regression because their `ConversationService` fixtures do not inject `learning_service`.
- Issue #34 assistant-only retry reuses `_reply_to_user_message()`, so a failed `/say` that later retries successfully is also currently eligible for learning extraction.

## Required design boundary

Use a deterministic persisted source/policy, not translated-text heuristics.

Preferred minimal shape:

- ordinary typed chat user messages keep an ordinary source such as `terminal` and remain eligible;
- `insert_translated_user_message()` persists the translated user message with an explicit source such as `say` / `translation`;
- the shared assistant reply path decides whether post-reply Issue #29 extraction is eligible from that persisted source (or an equivalently explicit argument that remains safe across assistant-only retry);
- assistant-only retry reads the same persisted user message and therefore cannot accidentally re-enable learning extraction for `/say`.

Do not add a database migration if the existing `Message.source` string column is sufficient.

## Required behavior

1. Successful `/say` still persists exactly one translated user message and one assistant response, but it creates zero conversation learning occurrences/items even if the provider proposes a valid bounded candidate.
2. `/say` partial failure still persists one translated user message; a later Issue #34 assistant-only retry may add the assistant but must still create zero conversation learning occurrences/items.
3. Ordinary `/messages` chat remains eligible for Issue #29 and creates exactly one occurrence/item when the same provider proposes a valid candidate.
4. Proactive conversation practice continues to use ordinary chat semantics, so its successful turn can create the occurrence that `finalize_practice()` resolves to `learning_signal_captured`.
5. `/help` and `/hint` assistance capture is unchanged.
6. Memory extraction remains unchanged; do not use this issue to exclude `/say` from long-term memory unless separate evidence requires it.
7. Existing chat error isolation, retry idempotency, grading, scheduler, memory recall, and proactive state must remain unchanged.

## Acceptance tests

Add production-equivalent deterministic integration coverage with a real `LearningService` injected into `ConversationService`.

At minimum prove:

### Successful `/say` exclusion

- provider returns a valid learning signal candidate bound to the actual conversation/user/assistant IDs;
- `/say` succeeds;
- stored messages are exactly one user + one assistant;
- translated user message has the explicit persisted source chosen for `/say`;
- learning occurrence count is zero and due learning count is zero.

### `/say` failure then assistant-only retry exclusion

- translation succeeds and user message persists;
- first assistant generation fails retryably;
- retry endpoint succeeds using the same persisted user-message ID;
- stored messages are exactly `[user, assistant]`, no duplicate translation;
- learning occurrence/item count remains zero after retry.

### Ordinary chat still learns

- with the same learning candidate policy/provider, a normal `/messages` turn creates exactly one provenance-backed occurrence/item and is due through existing readers.

### Proactive regression

- prefer one focused assertion that a normal proactive practice turn still creates an occurrence through `ConversationService` and can finalize as `learning_signal_captured`;
- do not manually insert the occurrence for this new regression test.

### Existing behavior

- `/help` and `/hint` learning tests remain green;
- `/say` retry idempotency remains green;
- greeting/noise gates remain green.

## Likely touch points

- `src/companion/conversation/service.py`
- optionally a small source constant/enum near conversation schemas if that avoids magic strings
- `tests/integration/test_m1_commands.py` or a new focused E2E integration test
- `tests/integration/test_conversation_learning_signals.py`
- `tests/integration/test_m4_proactive.py` only if needed for the production-path assertion
- test support provider sequencing only if necessary

## Non-goals

- No broad event bus or post-processing framework.
- No message threading migration.
- No LLM eligibility redesign.
- No changes to review grading/scheduling.
- No memory/proactive redesign.
- No semantic retrieval changes.

## Required verification

Run and report:

- focused `/say` + learning + proactive tests;
- `ruff check .`;
- strict `mypy`;
- full `pytest`;
- `git diff --check`;
- normal SQLite migration round-trip through repository CI (no migration expected).

## Delivery guard

This is one Codex implementation run for Issue #47. Implement production code/tests, do not merge, and preserve the completed task/commit if publication is blocked. ChatGPT owns complete GitHub-visible diff review, CI verification, focused fixes, and merge.