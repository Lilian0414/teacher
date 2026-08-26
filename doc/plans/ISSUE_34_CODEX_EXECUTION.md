# Issue #34 Codex execution contract

Source: GitHub Issue #34 — Make `/say` partial failures explicit and retry-safe.

Base: `main` at `3edc684ffdf453c9d4eb6522fd0525d62078a08a` after Issue #33 reached `main` and post-merge CI passed.

## Goal

Make `/say` truthful when translation succeeds but assistant generation fails, and provide an assistant-only retry path that can never append the translated user message a second time.

This is a narrow correctness/UX remediation. Preserve the existing language-help provider, ordinary conversation behavior, learning/memory semantics, and UI architecture unless a small refactor is required to reuse the normal assistant-generation/post-reply path safely.

## Verified current behavior

The current `/say` flow in `src/companion/api/routes.py` is:

1. `provide_language_help(SAY, original Chinese)` returns `natural_expression`.
2. `_execute_language_command()` calls `ConversationService.insert_translated_user_message(...)`.
3. `insert_translated_user_message()` delegates to the ordinary `send_user_message()` path.
4. `send_user_message()` persists the translated **user** message before it asks the chat provider for an assistant reply.
5. If assistant generation fails, `SendMessageResult` correctly contains the durable user message plus `error` / `retryable`, but `_execute_language_command()` discards `result.error` and always returns the success-only message `Inserted translated English into the conversation.`.
6. `CommandResponse.ok` becomes false, and the terminal UI's generic failure formatting therefore shows only that misleading success-only message. It does not expose the actual controlled assistant error, does not retain the durable user-message identity, and offers no safe retry.
7. Re-running the original `/say ...` command repeats translation and calls `send_user_message()` again, appending a duplicate translated user turn.

The API already has a useful ordinary-message result shape (`user_message`, optional `assistant_message`, `error`, `retryable`). Reuse those semantics rather than inventing an opaque retry token if the persisted user-message ID is sufficient.

## Core invariant

The retry identity is the **already persisted translated user message ID**.

A retry must never translate again and must never call the code path that appends a new user message.

Desired shape:

`/say Chinese`
→ translation succeeds
→ translated user message is durably persisted once
→ assistant generation succeeds **or** returns a controlled partial failure

If partial failure:

`retry existing translated user message ID`
→ validate it is still the retryable conversation tail
→ generate/persist assistant only
→ return the same user-message identity plus assistant/error state

No second user-message insertion is allowed.

## Required behavior

### 1. Make `/say` partial success explicit

When translation succeeds and the translated user message is persisted, but assistant generation fails:

- return a response that explicitly states translation/message persistence succeeded;
- return the actual controlled assistant-generation error separately from success text;
- expose the durable translated user-message identity needed for retry;
- keep `inserted_into_conversation=true` and the translated English text truthful;
- keep `ok=false` (or an equally explicit partial-success representation) so callers do not mistake the whole operation for success;
- preserve `retryable` from the assistant provider error;
- do not manufacture an assistant message from error text.

Naming may vary, but prefer explicit fields such as `inserted_user_message`, `inserted_user_message_id`, and/or `assistant_error` over encoding state only in a prose `message`.

If translation itself fails, or no translation is returned, behavior remains a normal pre-persistence failure: no user message and no assistant retry target.

### 2. Add assistant-only retry in `ConversationService`

Add a narrow service operation that retries assistant generation for an **existing persisted user message** without adding another user message.

It must validate at least:

- conversation exists and is not ended;
- target message exists in that conversation;
- target role is `user`;
- target is still the current retryable unanswered tail (or an equivalent deterministic condition proving no later user turn superseded it).

A practical no-migration policy is acceptable:

- if the target user message is the last conversation message, generate one assistant reply;
- if the target is immediately followed by the already-generated assistant and no later conversation activity exists, return that existing assistant idempotently instead of generating another;
- if later/unrelated conversation activity exists, reject retry with a deterministic conflict rather than attaching a reply to stale evidence.

Do not infer a retry target from translated text alone.

### 3. Reuse normal assistant/post-reply behavior

Avoid maintaining two divergent assistant-generation implementations.

A small internal refactor is encouraged if it lets both:

- ordinary `send_user_message()`; and
- assistant-only retry

share the same assistant generation + persistence + existing post-reply hooks.

Preserve whatever learning-signal behavior a successful ordinary translated turn currently receives; Issue #34 must not add a second learning path or deliberately redesign `/say` learning semantics.

Provider errors remain structured non-assistant data. Existing safe provider error formatting must continue to avoid credentials/secrets.

### 4. Add a narrow retry API

Expose the assistant-only retry through Core using the persisted conversation ID + user-message ID, for example:

`POST /v1/conversations/{conversation_id}/messages/{user_message_id}/retry-assistant`

The exact route/name may differ if an existing API shape is cleaner.

Response should clearly contain:

- the existing user message;
- optional assistant message;
- controlled error;
- retryability / completion state.

Use explicit status codes for invalid/stale retry evidence (404/409/422 as appropriate). A provider failure may remain a normal structured response consistent with the existing `/messages` endpoint rather than turning provider text into an HTTP exception.

### 5. Make terminal UI truthful and retryable

When `/say` returns partial success, the terminal UI must show both facts, for example:

- `You said: <translated English>`
- `[system] Assistant reply failed: <controlled error>`

and expose a clear retry action when retryable.

The UI must persist the pending retry state locally using the conversation ID + persisted user-message ID returned by Core. Pressing retry must call the assistant-only retry endpoint, not `/say` and not `/messages` with the translated text.

A small `Retry reply` action/button in normal mode is acceptable. Do not hide the existing Help/Hint/Review actions permanently; after retry succeeds (or Core reports an already-completed deterministic result), clear the pending retry state and restore normal actions.

If retry fails transiently, keep the same pending message ID so the next retry remains assistant-only.

If Core reports the retry is stale/conflicting, show that controlled result and do not append another user message.

### 6. Preserve scope

Do not change:

- translation prompt/provider behavior;
- `/help` or `/hint` semantics;
- review grading/scheduling;
- proactive practice state;
- memory recall (#33);
- memory extraction policy;
- persistence schema unless compelling evidence proves a message-parent linkage migration is necessary.

Prefer no migration for this issue if deterministic conversation-tail validation is sufficient.

## Acceptance tests

Add deterministic coverage proving at least:

### API partial failure

- translation succeeds;
- translated English user message is persisted exactly once;
- assistant provider fails;
- `/say` response reports `inserted_into_conversation=true`, the inserted text/message identity, the controlled assistant error, `ok=false`, and correct retryability;
- stored conversation contains exactly one translated user message and no assistant;
- provider error text is not persisted as an assistant message.

### Retry success without duplicate user message

Starting from that partial state:

- call the assistant-only retry for the returned user-message ID;
- provider succeeds;
- conversation becomes exactly `[user, assistant]`;
- the original user-message ID is unchanged;
- no second translated user message is created.

### Retry idempotency / stale protection

- repeating retry after a successful retry returns the existing assistant (or an equally safe completed result) and does not append another assistant;
- retrying an unrelated/non-user message is rejected;
- retrying after a later user turn supersedes the failed `/say` turn is rejected with a deterministic conflict;
- invalid conversation/message IDs are controlled.

### UI partial failure + retry

Use terminal UI tests with `httpx.MockTransport` proving:

1. `/say` command response indicates the translated user message was persisted but assistant failed;
2. UI renders the translated utterance and controlled assistant error;
3. UI retains the exact conversation/message retry evidence;
4. retry action calls only the assistant-only retry endpoint;
5. no second `/v1/commands/execute` `/say` call and no `/messages` POST occurs during retry;
6. transient retry failure preserves pending evidence;
7. successful retry renders the assistant and clears pending retry state.

### Regression

- normal successful `/say` remains one user + one assistant and UI output is unchanged or clearer;
- translation failure before persistence still creates no conversation message;
- `/help`, `/hint`, ordinary chat, and existing review/proactive tests remain green.

## Likely touch points

- `src/companion/conversation/service.py`
- `src/companion/conversation/repository.py` only if a narrow message lookup/order helper is needed
- `src/companion/api/routes.py`
- `src/companion/api/schemas.py`
- `src/terminal_ui/app.py`
- `tests/integration/test_m1_commands.py` and/or a focused conversation API test
- `tests/unit/test_terminal_ui.py`
- `tests/support.py` only for deterministic provider sequencing if needed

## Explicit non-goals

- No generic job/retry framework.
- No command idempotency token system.
- No broad message threading/reply graph unless unavoidable.
- No database migration just to model every possible chat parent/child relation.
- No LLM-based retry decision.
- No #33, review, proactive, or memory redesign.

## Required verification

Run and report:

- `ruff check .`
- strict `mypy`
- full `pytest`
- focused `/say` / conversation / terminal UI tests
- `git diff --check`
- migration round-trip only if a migration is unexpectedly added

Normal CI must remain offline and deterministic.

## Delivery / duplicate-run guard

- Use one active Codex implementation task by default.
- Implement production code/tests on a dedicated branch from `spec/issue-34-say-partial-failure-retry` and target that planning branch when publication controls are available.
- Do not merge. ChatGPT owns complete GitHub-visible diff review, CI verification, focused review fixes, and merge.
- If publication is blocked, preserve the completed task/commit and use the same Push/Create PR handoff later. Do not rerun implementation merely because remote publication fails.
- Do not broaden beyond Issue #34.