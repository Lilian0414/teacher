# Issue #53 — idempotent assistant retry across chat, practice, and /say

Source: GitHub Issue #53.

Base: current `main` after Issue #52 merge.

## Goal

Finish one consistent assistant-partial-failure contract across ordinary chat, proactive practice, and `/say` without creating duplicate user messages or duplicate assistant replies.

The Core already has a useful primitive: `ConversationService.retry_assistant_reply()` targets a persisted user message, returns the existing assistant when retry is repeated after success, rejects stale/non-tail/wrong targets, and does not run ordinary learning extraction for `source="say"`. Keep and reuse this primitive rather than creating a second retry path.

The known gaps are primarily at the terminal/API boundary:

- ordinary and proactive chat return a durable `user_message` on retryable assistant failure, but `_send_chat_message()` currently logs the error and discards that message ID;
- `_pending_assistant_retry` exists, but today it is populated only by the `/say` command path and the Retry action is restricted to normal mode;
- proactive practice therefore encourages re-entry of the answer, producing a second durable user message and potentially completing from the wrong evidence;
- `_execute_language_command()` catches `ConversationNotFoundError` for `/say`, but not `ConversationEndedError`, so `/say` after end can escape as HTTP 500 instead of a controlled 409.

## Required behavior

1. When ordinary or proactive chat persists a user message and assistant generation fails retryably, retain the exact `conversation_id` and `user_message_id` returned by Core.
2. Tell the user clearly that the message was saved and only the assistant reply failed. Present one Retry reply action bound to that persisted message.
3. Retrying must call the existing `/v1/conversations/{conversation_id}/messages/{user_message_id}/retry-assistant` endpoint. It must never resend the user's content or create a second user row.
4. Successful retry must append/render exactly one assistant reply. Repeating retry after success must reuse the same assistant result and never duplicate it.
5. Ordinary-chat retry success must preserve the normal learning-signal behavior associated with the original persisted user message. The retry itself must not create duplicate occurrences/items.
6. `/say` must preserve its current source semantics: one `source="say"` user row, assistant-only retry, and zero ordinary-conversation learning items/occurrences.
7. `/say` against an ended conversation must return HTTP 409 with a meaningful detail and no persistence changes.
8. Wrong-conversation, stale/non-tail, or ended-conversation retry must return the existing explicit 404/409 contract, leave persistence unchanged, and clear/disable stale UI retry state.

## Proactive practice contract

A retryable assistant failure during `PRACTICE_PROMPT` must not abandon practice mode and must not require the user to type the practice answer again.

- retain the original invitation ID plus the persisted user-message evidence;
- allow Retry reply while practice is active;
- after assistant retry succeeds, construct practice completion evidence from the **original user_message_id** and successful assistant ID;
- finalize through the existing practice-complete endpoint;
- finalization remains idempotent and happens at most once;
- if assistant retry becomes stale/invalid, surface the conflict and leave the invitation in a recoverable/explicit state rather than silently completing with new evidence.

Do not redesign proactive lifecycle here; Issue #54 owns exit/restart interruption safety.

## Preferred UI shape

Use the existing `_pending_assistant_retry` state rather than adding a parallel retry model. It may need additional context such as whether the pending retry belongs to ordinary chat or an active practice invitation.

Keep the action narrow:

- normal partial failure → Retry reply button/action;
- practice partial failure → Retry reply button/action while remaining in practice mode;
- `/say` partial failure → existing Retry reply behavior;
- after success or terminal 404/409 → clear the stale affordance.

Do not add automatic retries or silently retry in the background.

## API correction for /say

Map `ConversationEndedError` from `insert_translated_user_message()` to HTTP 409. Do not convert it to a successful `CommandResponse` with `ok=false`; the UAT contract specifically expects a controlled conflict status analogous to ordinary messaging.

Keep `ConversationNotFoundError` behavior explicit and stable. If existing command-routing conventions require a 404 for a missing conversation, prefer a real HTTP 404 over an ambiguous 200 command failure only if this can be done without broad command API churn; the required blocker for this issue is ended conversation => 409.

## Required tests

Add deterministic fail-once regressions through real service/API/UI wiring where practical.

### Ordinary chat

- first send persists exactly one user row and returns retryable assistant failure;
- UI retains that user ID and offers Retry reply;
- retry succeeds without adding a second user row;
- repeated retry returns/reuses the same assistant ID;
- final DB transcript is exactly one user + one assistant;
- learning signal/occurrence is at most once for that original pair.

### Proactive practice

- accepted practice invitation + fail-once chat persists one original user message;
- UI remains in practice mode with Retry reply available;
- retry succeeds for that original user ID;
- completion uses the original user ID + successful assistant ID;
- invitation outcome finalizes once;
- no second practice user message is introduced by retry.

### /say

- first `/say` persists one translated `source="say"` user row and fails assistant generation retryably;
- assistant retry succeeds for the same user ID;
- repeated retry reuses the same assistant ID;
- zero learning items/occurrences are created for `/say`;
- `/say` after ended conversation returns 409 and adds no message.

### Stale/wrong/ended retry

- wrong conversation / non-tail / ended targets retain explicit 404/409 semantics;
- persistence is unchanged;
- terminal UI clears the retry affordance after terminal conflict.

Assert exact message counts and IDs, not only status codes or rendered text.

## Non-goals

- No automatic retry loop.
- No provider redesign.
- No scheduler/review changes.
- No memory changes.
- No Help/Hint changes.
- No proactive quit/restart recovery redesign; that is #54.
- No database migration unless a truly necessary persistence invariant is discovered. The expected implementation should not need one.
- Do not work on #54 or #55.

## Verification

Run and report:

```bash
ruff check .
mypy .
pytest
TZ=Asia/Taipei pytest <focused issue-53 tests> -q
git diff --check
```

Keep the SQLite migration round trip green even though no migration is expected.

## Delivery model

Complete code and tests first in the Codex task. Do not spend effort creating, updating, or publishing PRs. Commit the finished work and stop with a concise summary containing exact branch/commit SHA, changed behavior/files, focused/full test results, and blockers.

If push/PR publication is unavailable, that is not task failure. Preserve the completed commit for the user to publish manually. Do not split Issue #53 into phases unless there is a genuinely independent blocker. Do not merge.
