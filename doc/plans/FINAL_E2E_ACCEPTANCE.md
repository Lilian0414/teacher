# Final E2E acceptance contract

Base: `main` at `4f42256b21ba401f68bd4d4e45dc20218e3824d9`, after final-audit fixes for Issue #47 and reopened Issue #33 were merged.

## Goal

Add executable cross-module acceptance coverage for the actual Teacher product loop. This is an acceptance/regression task, not a feature task.

Start by adding tests only. Do not change production code unless the new acceptance journey exposes a reproducible correctness failure on current `main`. If a production change becomes necessary, keep it minimal and report the exact failed invariant that required it.

## Product journey to prove

Use production-equivalent service/API wiring and one shared SQLite database/session state where practical. Deterministic fake providers are expected; no live Groq or Ollama calls.

### Journey A — conversation → learning → review → proactive behavior

1. Start a normal conversation through the real conversation path.
2. Send a substantive ordinary user turn.
3. Provider returns a valid learning-signal candidate bound to the real conversation/user/assistant IDs.
4. Prove one durable occurrence/item exists and is immediately due through the normal reader.
5. Review that same item through the normal review service/API, using a safe accepted variant such as a supported contraction.
6. Prove the attempt is persisted, stage advances, and the item is no longer immediately due.
7. With no due item and enough idle time, proactive check should offer conversation practice rather than review.
8. Start that invitation, send the practice response through `ConversationService.send_user_message()` (no manual occurrence insertion), and finalize practice with the real returned message IDs.
9. Prove finalization links the exact occurrence and reports `learning_signal_captured` when a candidate is produced.
10. After the accept cooldown, prove a newly due practice-created item changes future proactive behavior to a REVIEW invitation.

### Journey B — conversation end → memory → future paraphrase recall

1. During a real conversation, persist a user fact suitable for long-term memory.
2. End the conversation through the real memory-extraction path; provider returns a candidate with the actual source user-message ID.
3. Prove exactly one active memory is stored with source provenance.
4. Start a new conversation.
5. Use a deterministic embedding provider to ask a true zero-token-overlap paraphrase (for example stored `My favorite meal is salmon.` then query `What food do I like best?`).
6. Prove the stored fact reaches the actual chat system context; unrelated/deleted memory remains excluded.
7. No query-time memory writes/backfills are allowed.

### Journey C — `/say` partial failure/retry remains outside learning loop

Reuse the final-audit regression contract rather than duplicating all unit details:

1. `/say` (or the production-equivalent translated-message path) persists one translated user message with `source="say"`.
2. First assistant generation fails retryably.
3. Assistant-only retry succeeds using the same user-message ID.
4. Stored conversation is exactly `[user, assistant]`; no duplicate translation or assistant.
5. Even if the provider would propose a valid learning signal, zero ordinary-conversation learning occurrences/items are created for this `/say` turn.

## Coverage rules

- The proactive journey must not call `LearningRepository.capture_occurrence()` directly.
- The memory journey must not preinsert the target memory directly; it must come from conversation-end extraction.
- The semantic recall assertion must inspect the actual `ChatRequest` system context, not only call `MemoryContextBuilder.select()` in isolation.
- Keep memory and learning as separate stores/source-of-truth.
- Do not create a second mastery, grading, scheduling, memory, or proactive path.
- No network calls, sleeps based on wall clock, or flaky timing. Use injected clocks/events/fake providers.
- Prefer a focused new file such as `tests/integration/test_e2e_acceptance.py` rather than rewriting existing module tests.
- It is acceptable to split the journeys into 2–3 tests sharing one deterministic harness; do not force one giant unreadable test.

## Existing invariants that must remain green

- Ordinary conversation learning signal extraction is best-effort and idempotent.
- `/say` never creates ordinary-conversation learning signals, including after assistant-only retry.
- Help/Hint capture semantics remain unchanged.
- Review grading/scheduling stays deterministic.
- Proactive completion retry/abandon behavior remains unchanged.
- Semantic memory recall remains async, bounded and read-only at query time.
- Conversation-end memory extraction remains atomic/retry-safe.

## Required verification

Run:

- the new E2E acceptance test file;
- relevant existing learning/proactive/memory/`/say` integration tests;
- `ruff check .`;
- strict `mypy .`;
- full `pytest`;
- `git diff --check`;
- CI SQLite migration round trip.

## Delivery rule

Codex owns implementation of tests (and only evidence-required production fixes). Do not merge. Preserve the exact task/commit if publication is blocked. ChatGPT will independently review the complete GitHub-visible diff, test semantics and CI before deciding whether the product loop is accepted.