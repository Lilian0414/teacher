# Issue #30 Codex execution contract

Source: GitHub Issue #30 — Grade safe answer variants without corrupting learning state.

Base: `main` at `a203124f04098aaa586e2735bce3febd8ada81d9` after Issue #29 reached `main` and CI passed.

## Goal

Make review grading accept clearly equivalent, safely canonicalizable answer variants such as `I am tired.` and `I'm tired.` without weakening the deterministic learning-state transition model. Grading policy must remain explicit, bounded, testable, and Python-authoritative.

## Verified current behavior to preserve

- `LearningService.answer()` loads the due item and its existing accepted-answer list, then grades by normalized exact equality.
- `normalize_learning_text()` already handles whitespace, case folding, and terminal punctuation.
- Correct answers advance `stage`; incorrect answers reset `stage` to 0; interval calculation remains deterministic in Python.
- `LearningRepository.record_attempt()` performs a compare-and-update using the item's prior `stage` and `next_review_at`, then inserts the attempt in the same transaction. If the stale compare fails, it rolls back and raises `LearningItemNotDueError`.
- Accepted answer alternatives are already persisted as an explicit list on the learning item.
- Issue #29 now creates ordinary-conversation learning items through the same repository/review source of truth; do not add a separate grading path for those items.

## Required behavior

1. **Introduce an explicit grading-policy boundary**
   - Move answer-equivalence logic out of the scheduling/state-transition calculation into a small named policy/helper/module that can be unit-tested independently.
   - The policy should return a bounded deterministic result that `LearningService.answer()` consumes.
   - Do not couple grading-policy code to database writes or scheduling decisions.

2. **Keep exact accepted answers authoritative**
   - Any existing accepted answer must still grade correct after the repository's current text normalization.
   - Multiple explicitly stored accepted answers remain the strongest source of truth.
   - Do not synthesize broad semantic paraphrases that were never accepted by the learning item.

3. **Support only safe deterministic canonical variants**
   - Add bounded canonicalization for clearly equivalent forms needed for normal English review, including at minimum `I'm` ↔ `I am` so the reproduced audit case passes.
   - It is acceptable to support a small documented set of unambiguous contractions/expansions (for example `you're`/`you are`, `we're`/`we are`, `they're`/`they are`, common `not` contractions) when equivalence is deterministic.
   - Avoid blindly canonicalizing ambiguous contractions such as `'s` where the expansion may be `is` or `has`, unless the implementation can prove the variant safely from the accepted answer itself without semantic guessing.
   - Do not use edit distance, fuzzy substring matching, token-overlap thresholds, embeddings, or a general semantic similarity score for correctness.

4. **Ambiguous or unsupported variants must fail safely**
   - If the submitted answer cannot be proven equivalent by the bounded deterministic policy or an explicitly stored accepted answer, it must not be silently marked correct.
   - Ambiguous cases should remain ordinary incorrect results under the current product contract rather than invoking an unbounded judge.
   - Do not add a live LLM judge in this issue unless repository evidence demonstrates deterministic policy is insufficient for the acceptance criteria. If a judge is nevertheless introduced, it may only return evidence/score; Python must remain authoritative and provider failure must not partially mutate learning state.

5. **Preserve atomic state transitions and stale-answer protection**
   - Do not weaken or bypass the `record_attempt()` compare-and-update semantics.
   - One accepted grading decision must still produce exactly one atomic item-state update + attempt record.
   - A stale duplicate submission must still fail without adding another attempt or changing stage/schedule.
   - A grading-policy exception/failure must occur before persistence so it cannot partially mutate the item.

6. **Keep scheduling unchanged**
   - Correct answer: preserve the existing stage advancement and interval policy.
   - Incorrect answer: preserve reset to stage 0 and current one-day reschedule behavior.
   - Do not redesign spaced repetition, mastery, due selection, proactive scheduling, or learning-item identity.

7. **Feedback remains truthful**
   - Preserve the existing `ReviewResult` contract unless a minimal additive field is genuinely needed to explain why a variant was accepted.
   - The user should be able to see whether the answer was accepted and the explicit accepted answers without exposing internal prompts or provider internals.
   - Do not add verbose debug reasoning to normal UI output.

## Acceptance tests

Add deterministic coverage proving at least:

- accepted `I am tired.` + submitted `I'm tired.` grades correct, advances stage exactly once, schedules according to the existing correct-answer policy, and records a correct attempt;
- the reverse safe direction (`I'm tired.` accepted, `I am tired.` submitted) is handled if the policy is bidirectional;
- already-supported whitespace/case/terminal-punctuation normalization still passes;
- an explicitly stored alternate accepted answer still passes without needing contraction logic;
- a genuinely wrong answer still grades incorrect, resets stage, schedules according to the existing policy, and records an incorrect attempt;
- an ambiguous/unsupported form does not become correct merely because it is lexically similar;
- a stale duplicate answer after a successful attempt still raises `LearningItemNotDueError` and creates no extra attempt/state mutation;
- a grading-policy failure injected before persistence leaves item state and attempts unchanged;
- existing conversation-derived items from #29 use the same grading path/source of truth (a focused integration assertion is enough; do not duplicate #29's extraction tests).

## Likely touch points (not a required file list)

- `src/companion/learning/service.py`
- `src/companion/learning/normalization.py` or a new narrowly named grading module
- `src/companion/learning/schemas.py` only if a minimal result/feedback addition is justified
- `tests/unit/test_learning.py`
- focused integration test only if needed to prove #29-created items use the same path

Prefer existing abstractions and the smallest clear implementation.

## Explicit non-goals

- No scheduling redesign.
- No mastery model changes.
- No proactive practice work (#31).
- No semantic memory retrieval work (#33).
- No `/say` reliability work (#34).
- No broad LLM-as-judge system, embeddings, vector similarity, fuzzy matching framework, grammar engine, event bus, or agent framework.
- No UI redesign.
- No database migration unless a genuinely necessary additive feedback field cannot be represented otherwise; no migration is expected.

## Required verification

Run and report exact results for the strongest applicable repository gates:

- `ruff check .`
- strict `mypy` using the repository's configured command
- `pytest`
- focused grading tests
- `git diff --check`
- migration round trip only if a migration is introduced (not expected)

If a layer cannot run, report it exactly; do not claim unexecuted checks passed.

## Delivery / duplicate-run guard

- This scoped issue gets one active Codex implementation task/writer by default.
- Production implementation belongs on a dedicated child branch from `spec/issue-30-safe-answer-grading` and should target that planning branch.
- Do not merge. ChatGPT owns complete diff review, CI review, and merge decisions.
- Publication failure is not an implementation failure. Preserve the completed task/commit and reuse the same task's Push/Create PR controls rather than reimplementing.
- Do not broaden into #31/#33/#34 or unrelated cleanup.