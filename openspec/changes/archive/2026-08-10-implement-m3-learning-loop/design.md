## Context

The M2 baseline already separates FastAPI Core, the Textual HTTP client, SQLAlchemy repositories,
LLM providers, an injected clock, conversation history, and long-term life-memory context. M3 spans
those layers and adds durable scheduling data, so a design artifact is warranted. See
`proposal.md` for motivation and `specs/learning-loop/spec.md` for observable behavior.

## Goals / Non-Goals

**Goals:**

- Keep persistence and policy in Core while the terminal owns only transient presentation state.
- Make every scheduling and answer-evaluation decision deterministic and testable with an injected
  clock and the fake provider.
- Preserve the distinction between language-learning data and long-term life memory.
- Allow a stopped review to resume safely without persisting a separate session object.

**Non-Goals:**

- Persisting a cursor, background review session, or terminal UI state.
- Semantic or LLM-based grading of approximate answers.
- Active reminders, scheduled invitations, DND-aware outreach, voice, hardware, or file tools.
- Replacing the existing relevance algorithm with embeddings or a vector database.

## Decisions

### Store learning items and attempts in separate relational tables

Add `learning_items` for the current prompt, accepted-answer JSON, kind, source command, stage, and
next-review timestamp. Add append-only `learning_attempts` linked to the item with the submitted
answer, correctness, stage transition, and attempt timestamp. A uniqueness constraint on
`(user_id, normalized_prompt, kind)` enforces deduplication; repository-level merging preserves a
portable implementation across SQLite tests and the local database.

Alternative considered: reuse `memories`. Rejected because learning expressions are not life facts,
have different retention and scheduling semantics, and must never enter M2 extraction or search.

### Keep review sessions transient and item-addressed

`/review` asks Core for the earliest due item. The response carries structured review data. The
terminal stores only that active item identifier; the next non-command input is posted to a review
answer endpoint. Core verifies that the item exists and is due, records the attempt atomically,
updates its schedule, and returns feedback plus the next due item. `/review quit` clears only the
terminal's active identifier. Slash commands are still sent to command execution and do not clear
the active item.

Alternative considered: persist a review-session row and cursor. Rejected because unanswered items
remain due naturally, answered items persist their new date, and ordering is deterministic; a
session table would add lifecycle and stale-session cleanup without improving recovery.

### Grade locally against normalized accepted answers

Learning creation maps provider output into accepted answers: `/help` uses a natural expression,
correction, alternatives, or the original already-correct English input; `/hint` uses each returned
hint. Core normalizes case, whitespace, and terminal punctuation before exact comparison. It reveals
the accepted answers only after an attempt.

Alternative considered: ask Groq to grade semantic equivalence. Rejected for M3 because grading
would be nondeterministic, add latency and API cost, complicate offline behavior, and make ordinary
tests depend on provider judgment.

### Use a stage-based interval table

The service owns a constant interval sequence of 1, 3, 7, 14, and 30 days. Items start at stage
zero and due immediately. Correct attempts increment the stage and select the corresponding capped
interval; incorrect attempts reset to stage zero and use one day. The injected clock supplies every
timestamp.

Alternative considered: SM-2 ease factors. Rejected because confidence grading and tunable quality
scores are not part of the approved milestone; the fixed policy is explainable and sufficient for
the first closed loop.

### Compose learning and life-memory context without merging their stores

A learning context builder selects a small number of due items in deterministic order. The
conversation service combines its output with the existing relevant-memory context as separately
labelled system guidance before the recent-message window. Each builder retains its own configured
limit and eligibility rules.

Alternative considered: copy learning items into memory so the existing builder can retrieve them.
Rejected because it violates the privacy/data-boundary requirement and would expose review examples
to memory extraction, search, and deletion semantics.

## Risks / Trade-offs

- [Exact local grading rejects valid paraphrases] → Show accepted answers immediately, keep the
  first version predictable, and leave semantic grading for a separately approved change.
- [JSON answer storage is less queryable] → Keep answer sets small and treat them as item payload;
  attempt history remains normalized for reporting and later migration.
- [Two clients can answer the same due item concurrently] → Validate due state and update the item
  plus attempt in one transaction; the second stale submission receives a conflict response.
- [Repeated help can unexpectedly make an item due] → This is intentional evidence of renewed
  difficulty; preserve history while moving `next_review_at` no later than the current time.
- [More system context can crowd recent chat] → Enforce small independent limits and omit empty
  sections.

## Migration Plan

1. Apply an additive Alembic migration that creates both learning tables and indexes; existing M0–M2
   data is unchanged.
2. Deploy Core and terminal changes together so structured review payloads are understood.
3. Roll back by reverting the application and running the migration downgrade, which removes only
   M3 learning items and attempts.
