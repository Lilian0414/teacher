# Issue #54 — make proactive practice interruption and restart safe

Source: GitHub Issue #54.

Base: current `main` after Issue #53 merge.

## Goal

Make proactive conversation-practice crash-safe without adding background jobs or a parallel workflow system. A conversation invitation that reaches `accepted` must never become a permanent orphan after graceful quit, assistant failure, or process restart.

This is one implementation task. Do not split it into phases unless a genuinely independent blocker is discovered.

## Current evidence / boundary

The existing invitation row already has nullable `conversation_id`, `user_message_id`, and `assistant_message_id` fields. However, `respond(..., start)` currently changes only the status to `accepted`; it does not bind the practice invitation to the active conversation. Message/evidence IDs are written only by `finish_practice()`.

Therefore restart recovery cannot safely guess which durable messages belong to an accepted invitation. Fix the missing durable association rather than inferring from unrelated conversation history.

## Required state contract

### 1. Bind conversation when conversation-practice starts

- Extend the START request only as much as necessary so a conversation invitation is accepted with the active `conversation_id` already persisted on the invitation.
- Validate that the conversation belongs to the configured user.
- A conversation START without a valid conversation id must fail explicitly (4xx) and must not leave an accepted orphan.
- Review invitations keep their existing behavior and do not require a conversation id.
- Preserve existing snooze and dismiss semantics.

Prefer reusing the existing `ProactiveInvitation.conversation_id` column. No schema migration should be needed unless repository evidence proves otherwise.

### 2. Deterministic restart reconciliation

Add one service-level reconciliation operation for stale `accepted` conversation invitations. Invoke it during the normal startup/conversation-creation path before the next UI session proceeds.

For each stale accepted conversation invitation:

- If it has no valid bound conversation, reconcile to terminal `abandoned`.
- Inspect only durable messages belonging to the bound conversation and created at/after the invitation's `responded_at` boundary.
- If there is one unambiguous practice user message followed by its assistant reply, finalize using those exact IDs through the existing `finalize_practice()` contract.
- If there is no complete usable user+assistant evidence (for example no answer, or assistant partial failure with only the user message), reconcile to terminal `abandoned` without creating a learning occurrence.
- If durable evidence is ambiguous rather than safely attributable, do not guess; reconcile to `abandoned` (or return a controlled conflict if that is required to avoid destructive ambiguity). Document whichever deterministic rule is used.
- Repeated reconciliation must be idempotent.

Do not create a second grading/learning-signal path. Successful recovery must reuse the same existing practice finalization and validated-evidence logic used by the live path.

### 3. Graceful quit

Update the terminal quit path so an active proactive conversation practice is resolved before the UI exits:

- If complete practice evidence is already pending, finalize it first.
- If the practice has no complete evidence (including a pending assistant retry), abandon the invitation.
- Only after the invitation is terminal should the normal conversation-end / memory-extraction path proceed.
- If Core cannot confirm either finalize or abandon, do not silently exit while leaving a known active invitation; show a recoverable system message instead.

Do not weaken the Issue #53 assistant-retry contract while the UI remains open. A retryable assistant failure still keeps the original user-message ID and offers Retry reply. This Issue only defines what happens if the user quits/restarts before that retry succeeds.

### 4. Active invitation invariant

- An `accepted` conversation invitation counts as active work and must not allow another conversation-practice invitation to be created for the same user before reconciliation/terminalization.
- Pending/snoozed/dismissed/completed/abandoned behavior must otherwise retain current eligibility/cooldown semantics.

## API / repository expectations

Keep API changes minimal. Likely touch points include:

- `ProactiveRespondRequest` / respond route for optional-or-required `conversation_id` on START;
- `ProactiveService.respond()` and repository resolution so conversation START persists the association atomically with acceptance;
- repository queries for accepted conversation invitations and deterministic post-acceptance message evidence;
- one service reconciliation method called from the existing conversation-startup path;
- terminal invitation START payload and graceful `action_quit()` handling.

Do not introduce a new background scheduler, queue, workflow engine, or a second persistence source of truth.

## Required regressions

Add service/API/persistence tests using a real temporary SQLite database where practical for:

1. START conversation practice persists the active conversation id atomically.
2. START with missing/wrong-user conversation is rejected without changing pending invitation state.
3. Graceful quit before any practice answer -> invitation becomes `abandoned`, conversation still ends normally.
4. Graceful quit after retryable assistant failure -> invitation becomes `abandoned`; saved user message remains single/durable; no learning occurrence is invented.
5. Graceful quit with complete pending evidence -> finalizes once with exact user/assistant IDs.
6. Forced interruption/restart with accepted + no answer -> startup reconciliation abandons it.
7. Forced interruption/restart with accepted + user-only partial failure -> startup reconciliation abandons it with zero new occurrence.
8. Forced interruption/restart with accepted + one durable user/assistant pair -> startup reconciliation finalizes exactly once from those IDs; repeating startup does not duplicate occurrence/outcome.
9. Ambiguous post-acceptance message history is never guessed into a completion.
10. While an accepted invitation exists, eligibility/check cannot create another active conversation invitation.
11. Existing snooze, dismiss, abandon twice, complete twice, and illegal transition tests remain green.
12. Terminal UI restart/quit tests assert visible action/state agrees with persisted invitation state.

Assertions must include exact invitation status/outcome, bound conversation id, user/assistant evidence IDs, learning occurrence count/ID where applicable, and conversation ended state.

## OpenSpec

Update the proactive-learning contract with an explicit state machine / restart rule:

`pending -> accepted -> completed | abandoned`

with snooze/dismiss remaining existing terminal/suppression branches, and with restart reconciliation defined for stale `accepted` conversation practice.

Document that completion requires attributable durable evidence and that absence/ambiguity is never converted into a learning occurrence.

## Non-goals

- No proactive eligibility/cooldown redesign beyond preventing a second active invitation.
- No scheduler redesign.
- No memory redesign.
- No new retry path; reuse Issue #53.
- No live Groq/Ollama acceptance; that belongs to #55.
- No unrelated timezone/UI-format fix; that belongs to #55.

## Verification

Run and report:

```bash
ruff check .
mypy .
pytest
TZ=Asia/Taipei pytest <focused issue-54 tests> -q
git diff --check
```

Also run the repository's SQLite migration round trip and strict OpenSpec validation if available.

## Delivery model

Complete code/tests/spec first and commit the finished work. Do not spend effort creating or updating another PR. If push/Create PR is unavailable, that is not a task failure: preserve and report exact branch + commit SHA + test results. Do not merge.