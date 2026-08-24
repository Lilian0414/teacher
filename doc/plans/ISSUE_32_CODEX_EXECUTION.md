# Issue #32 Codex execution contract

Source: GitHub Issue #32 — Constrain memory updates and make extraction atomic and recoverable.

## Goal

Make each memory-extraction attempt safe, atomic, recoverable, and retryable without introducing a second memory system or broad architecture rewrite.

The audit reproduced two correctness failures that must both be eliminated:

1. The provider can return `updates_memory_id` for an active memory that was not in the exact memory set offered to the provider, and the service may update that unseen row.
2. Earlier candidates can persist before a later candidate fails (for example an ambiguous ID), leaving a partial batch while the conversation/extraction state remains pending.

## Ownership

- ChatGPT: planning, GitHub orchestration, complete diff review, CI review, merge.
- Codex: production implementation and tests.
- Do not implement production changes on this planning branch.

## Required behavior

1. Build an allowlist from the exact memory records exposed to the provider for that extraction attempt. Any update target outside that allowlist must be rejected before the target row changes.
2. Define one explicit transaction/savepoint boundary covering candidate validation/persistence and extraction finalization so a candidate failure cannot leave an undocumented partial batch.
3. Ensure every started extraction reaches a durable terminal state (`success` or `failed`, using the repository's existing vocabulary/data model where possible). Do not leave an application-owned validation/persistence failure indefinitely as `pending`.
4. Retrying a failed attempt must be idempotent: no duplicate memories/occurrences and no re-application of already-aborted partial work.
5. Preserve existing soft-delete behavior, source-message validation, exact-duplicate handling, and the provider/error boundary.
6. Surface a bounded failure/retry state through the existing API/frontend path. Do not redesign the UI; add only the minimum truthful affordance needed to distinguish failed extraction from pending/success and to retry safely.
7. Keep database changes minimal. If a schema change is genuinely necessary, include a reversible Alembic migration and migration round-trip coverage; do not add schema changes merely for convenience.

## Required tests

Add integration/regression coverage proving at least:

- unauthorized `updates_memory_id` outside the offered set changes no target row;
- a later malformed/ambiguous candidate rolls back the whole attempted batch;
- failed extraction has a durable failed state;
- retry after failure is idempotent and can complete cleanly;
- restart/reload observes the same durable terminal state;
- existing deleted-memory, source-message, and duplicate semantics remain intact;
- API/UI response exposes bounded failure/retry semantics without leaking provider payloads or secrets.

Run and report exact results for:

- `ruff check .`
- `mypy .`
- `pytest`
- `git diff --check`
- migration round trip if any migration is added

## Explicit non-goals

- No learning-signal work (#29).
- No review grading changes (#30).
- No proactive conversation loop changes (#31).
- No semantic recall redesign (#33).
- No `/say` retry work (#34).
- No vector database, event bus, agent framework, broad repository refactor, or provider redesign.

## Delivery and sandbox-safe transport

Create a focused implementation branch from this planning head, preferably `codex/issue-32-memory-atomicity`, and a child PR targeting `spec/issue-32-memory-atomicity` if the environment can publish it. Do not merge.

Because Codex sandboxes may not have an authenticated Git remote, GitHub publication is not the only acceptable transport. After implementation and tests, always produce the complete unified diff against the planning head and serialize it as gzip + base64. In the final response include these markers on separate lines:

`BEGIN_GZIP_BASE64_PATCH`
`<single complete base64 payload>`
`END_GZIP_BASE64_PATCH`

Also report:

- SHA-256 of the decompressed unified diff;
- local implementation commit SHA, if a commit was created;
- exact test results;
- whether a GitHub child PR was actually published.

The transport payload must contain the complete implementation/test diff, without omitted hunks, secrets, API keys, or captured private conversation data. ChatGPT will mechanically transport the exact Codex-authored patch to GitHub if publication is unavailable.
