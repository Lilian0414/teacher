# Issue #52 — keep /help and /hint as distinct learning goals

Source: GitHub Issue #52.

Base: current `main` after Issue #51 Phase 2 merge.

## Goal

Fix learning-item identity so the same normalized source prompt can own separate learning goals when their kinds differ. `/help` expression output and `/hint` phrase/vocabulary output must not collapse into one item or share accepted answers.

## Required behavior

1. Identity/deduplication must be kind-aware. Preferred key: `(user_id, normalized_prompt, kind)`.
2. Same prompt + same kind remains idempotent and reuses the existing item.
3. Same prompt + different kind creates/reuses distinct items with independent accepted answers, stage, attempts, due date, and scheduling.
4. In the known reproduction, `/help 我今天很累` may create an expression item for `I am tired today.` while `/hint 我今天很累` creates a phrase/vocabulary item such as `tired` / `exhausted`; `tired` alone must not grade correct for the expression item.
5. Preserve the current deterministic review scheduler; do not redesign grading or intervals.

## Migration

Add a forward migration for existing databases. Update the persistence-level uniqueness/index contract to include `kind`. Preserve existing learning rows, attempts, stage, due dates, provenance/occurrences, and IDs whenever possible.

Existing rows cannot be retroactively split reliably when prior `/help` and `/hint` answers were already merged. Do not invent provenance. Keep each legacy row deterministically as its stored kind and preserve its state; after migration, future captures of another kind for the same prompt must create a distinct item. Document this behavior in the migration/spec/tests.

Migration must round-trip through the repository's normal CI migration check.

## Required tests

Add focused coverage at persistence/service/API level for:

- same prompt + expression then phrase/hint => two different item IDs;
- accepted answers remain isolated by kind;
- same prompt + same kind repeated => one reused item;
- expression review does not accept a vocabulary-only answer from the hint item;
- stages/due dates can advance independently;
- migration preserves existing item IDs, attempts, stages, due dates, occurrences/provenance and allows a post-migration second kind for the same prompt;
- existing review schedule transitions stay unchanged.

Use a deterministic provider and real repository/service wiring where practical. Do not solve this only with a mocked repository.

## OpenSpec/domain contract

Update the relevant OpenSpec/domain documentation so learning-item identity, deduplication, accepted-answer ownership, and legacy migration behavior match the implementation.

## Non-goals

- No scheduler redesign.
- No proactive changes.
- No memory changes.
- No `/say`/assistant-retry changes.
- No broad provider/prompt redesign.
- Do not work on #53-#55.

## Verification

Run and report:

```bash
ruff check .
mypy .
pytest
TZ=Asia/Taipei pytest <focused issue-52 tests> -q
git diff --check
```

Also verify a fresh SQLite migration to head and the normal migration round trip.

## Delivery model

Complete code, migration, tests, and spec update first. Commit the finished work in the Codex task. Do not spend effort creating or updating PRs. If push/publication is unavailable, that is not a task failure: preserve the commit and report exact branch/commit plus test results. Do not split Issue #52 into phases unless a genuinely independent blocker is discovered; the intended result is one completed implementation task. Do not merge.