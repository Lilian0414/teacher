# Issue #29 Codex execution contract

Source: GitHub Issue #29 — Create trustworthy learning signals from ordinary conversation.

Base: `main` at `a56b6322eb17ec8361995818f4caf9a6807a583d`.

## Goal

Allow one ordinary successful conversation turn to produce at most a small, trustworthy learning signal that enters the existing `LearningItem` / due-review loop, with durable provenance and retry-safe deduplication. The LLM may propose learning evidence, but Python owns whether anything is persisted and all learning state transitions.

## Current behavior to preserve

- `ConversationService.send_user_message()` persists the user message, generates the reply, then persists the assistant message.
- `LearningService.capture_assistance()` is currently the only production creator of learning items and uses `LearningRepository.upsert_item()`.
- `LearningItem` identity/deduplication is based on `user_id + normalized_prompt`; review state (`stage`, `next_review_at`) is deterministic Python state.
- Due-learning context and `/review` already read from the existing learning repository.
- Issue #32 atomic-memory changes are already on `main`; do not mix memory work into this issue.

## Required behavior

1. **Explicit, bounded signal contract**
   - Add a structured provider/service contract for ordinary-conversation learning evidence.
   - Prefer one candidate or no candidate per completed user/assistant turn for this MVP.
   - Candidate fields may describe bounded learning evidence such as kind, review prompt, accepted answer(s), and a reason/category.
   - The provider must not be able to set `stage`, mastery, `next_review_at`, due eligibility, review interval, or other scheduler state.

2. **Python-side eligibility gate**
   - Persist only candidates that pass deterministic validation in Python.
   - Bind provenance to the exact current conversation turn; reject source identifiers that do not match the offered/current turn.
   - Reject empty/trivial/non-reviewable candidates. Normal greetings/chitchat must not create noise.
   - Keep the accepted learning-signal reasons/categories bounded rather than accepting arbitrary state-changing instructions from the model.

3. **Conversation reply remains primary**
   - Persist and return a successful assistant reply independently of learning-signal extraction.
   - Learning extraction/provider/persistence failure must not erase, disguise, or turn an otherwise successful chat reply into a failed message request.
   - Keep post-processing narrow; do not introduce an event bus, job framework, or agent framework.

4. **Provenance and idempotency**
   - Persist durable provenance that can identify the source conversation and source user message (and assistant message when useful), plus why the signal was accepted.
   - Use the smallest schema addition needed. A dedicated learning occurrence/provenance record is acceptable and likely clearer than overloading review state, but the exact name/design is implementation-owned.
   - Enforce retry safety at the database/repository boundary so reprocessing the same source turn cannot create duplicate occurrences or duplicate learning items.
   - Reuse `LearningRepository.upsert_item()` / normalized prompt identity rather than creating a second learning-item source of truth.

5. **Existing review semantics remain authoritative**
   - New conversation-derived items must enter the same `LearningItem` table and become visible through the existing due-learning context and review readers.
   - Initial stage/due behavior must be created by existing deterministic Python rules, not copied from model output.
   - Do not change review grading in this issue (#30 owns that work).

6. **Provider implementation**
   - Extend the provider protocol/fake/test provider and Groq implementation only as needed for the bounded learning-signal contract.
   - Structured-output parsing must fail safely: malformed/noisy provider output means no learning mutation, while the already-successful assistant reply remains successful.
   - Do not require a live provider call for CI; use deterministic fake/unit/integration coverage. Live tests remain optional when credentials are genuinely available.

## Acceptance tests

Add deterministic coverage proving at least:

- an ordinary conversation turn with eligible structured evidence creates one learning item through the existing repository path;
- the persisted provenance identifies the source conversation/message and bounded acceptance reason;
- the created item is visible to existing due-learning context and/or `/review` readers;
- a greeting/non-learning turn creates no item and no provenance occurrence;
- processing the same completed turn twice is idempotent (one occurrence, no duplicate item/answers);
- provider extraction failure or malformed output does not change a successful assistant reply into an API failure and creates no partial learning mutation;
- invalid/unoffered source identifiers are rejected without learning mutation;
- existing Help/Hint capture behavior still works;
- migration upgrade/downgrade round trip passes if a schema migration is introduced.

## Likely touch points (not a required file list)

- `src/companion/conversation/service.py`
- `src/companion/learning/service.py`
- `src/companion/learning/repository.py`
- `src/companion/learning/schemas.py`
- `src/companion/providers/protocols.py`
- `src/companion/providers/groq.py`
- fake/recording provider support
- persistence model + Alembic migration if provenance needs schema
- focused unit/integration tests

Prefer existing abstractions; do not change unrelated modules merely to match this list.

## Explicit non-goals

- No review answer-variant/grading changes (#30).
- No semantic memory recall work (#33).
- No proactive conversation outcome loop (#31).
- No `/say` retry/partial-failure work (#34).
- No broad memory refactor, vector database, event bus, background worker framework, or generic agent architecture.
- No UI redesign.

## Required verification

Run and report exact results for the strongest applicable repository gates, normally:

- `ruff check .`
- strict `mypy` using the repository's configured command
- `pytest`
- `git diff --check`
- SQLite/Alembic migration round trip if a migration is added

If the environment cannot install dependencies or run a layer, report that exact layer as unverified; do not fabricate a pass.

## Delivery / duplicate-run guard

- This scoped issue gets one active Codex implementation task/writer by default.
- Before implementation, reuse any existing equivalent implementation branch/PR/task rather than opening duplicate work.
- A second implementation run requires a code-level reason from review, or proof that the first implementation artifact is genuinely unrecoverable.
- Missing PR controls, wrong branch placement, mobile publication limits, duplicate CI, or transport friction are **not** reasons to rerun implementation.
- Normal successful delivery should publish a branch/PR when possible. Do **not** emit a full unified diff/full-file/gzip-base64 bundle by default.
- If publication is blocked after valid implementation exists, preserve that implementation and use this recovery order: existing GitHub-visible commit/branch → same-task desktop Push/Create PR → mechanical GitHub branch/PR repair → already-produced exact transport artifact → new implementation run only as a last resort.
- Do not merge. ChatGPT owns complete GitHub diff review, CI review, and merge decisions.
