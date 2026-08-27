# Issue #55 — final UAT preparation

Source: GitHub Issue #55.

Base: current `main` after Issues #51–#54 are merged.

## Goal

Prepare Teacher for the final target-Mac acceptance run without pretending that CI or Codex can substitute for real macOS/Groq/Ollama UAT.

This task has two deliverables only:

1. remove the known timezone-dependent UI/test defect and define one explicit product timezone contract;
2. make the final UAT reproducible and evidence-driven with small preflight/snapshot tooling and documentation.

The actual final pass/fail decision for Issue #55 still requires a real run on the user's target Mac with `Asia/Taipei`, real Groq credentials, and real Ollama `nomic-embed-text`.

## 1. Timezone contract

Use `Settings.timezone` as the product display timezone for user-visible review due timestamps. Do not depend on the process/runner's implicit local timezone and do not use bare `datetime.astimezone()` when rendering product timestamps.

For the documented target profile, `Settings.timezone=Asia/Taipei` means review due timestamps shown to the user are converted to Asia/Taipei and include an explicit zone indication (for example `2026-08-10 20:00 Asia/Taipei` or an equally unambiguous representation).

Keep persisted timestamps and scheduling arithmetic in their existing canonical form; this task is about display/portability, not scheduler redesign.

Required deterministic coverage:

- the same stored review due instant renders identically when tests run under host `TZ=UTC` and host `TZ=Asia/Taipei` if `Settings.timezone` is the same;
- changing `Settings.timezone` intentionally changes the displayed local time/zone;
- no review answer is revealed before the user attempts the review;
- existing stage/due scheduling semantics remain unchanged.

Fix the known environment-sensitive assertion in `test_review_question_and_feedback_are_rendered_without_early_answers` by asserting the explicit product contract rather than an implicit runner-local hour.

## 2. Reproducible final-UAT support

Add a small, maintainable final-UAT guide and only the tooling that materially reduces manual ambiguity.

Preferred artifacts:

- `doc/FINAL_UAT.md` with exact clean-install/start commands for macOS, fresh DB migration, `Asia/Taipei`, Groq, and Ollama/nomic-embed-text;
- a small script or command (Python preferred if useful) that performs **preflight/read-only evidence checks**, such as printing the current commit, effective configured timezone/provider/model/embedding endpoint/model, database path, Alembic head/current revision if accessible, and Core health/state. It must redact secrets and must not mutate learning/memory/proactive state;
- a documented DB snapshot/query procedure for capturing counts/IDs/state needed by Issue #55 (messages, learning items/occurrences/attempts, memories/embedding metadata, proactive invitations/outcomes).

Do not build a UI automation framework just for this issue. Do not attempt to automate screenshots or a real Textual interactive session unless a very small existing test seam already makes it trivial.

## 3. Final UAT matrix

`doc/FINAL_UAT.md` must preserve the seven Issue #55 sections and make each one evidence-based:

1. ordinary chat + learning capture;
2. help → hint → review;
3. review correctness/scheduling;
4. proactive end-to-end + interruption recovery;
5. cross-conversation semantic memory recall and false-positive check;
6. `/say` + assistant retry across say/chat/practice;
7. UI/Core/database consistency.

For each section include:

- exact user action;
- expected UI behavior;
- relevant API status/result to record;
- persistence assertions to record;
- PASS/FAIL field;
- notes/evidence field.

Do not mark any live-provider or real-UI item PASS from automated tests alone.

## 4. Provider/live-run boundaries

The live target profile should document, not fake:

- real Groq credentials/model actually used;
- real local Ollama availability;
- `nomic-embed-text` model availability and configured embedding model/dimensions;
- semantic recall query with genuine zero direct lexical overlap;
- lexical fallback behavior when embeddings are unavailable may be checked separately, but does not replace the real semantic run.

Never print API keys/tokens. Any evidence command must redact secrets.

## 5. Automated verification before live UAT

Run and report:

```bash
ruff check .
mypy .
pytest
TZ=UTC pytest tests/unit/test_terminal_ui.py -q
TZ=Asia/Taipei pytest tests/unit/test_terminal_ui.py -q
TZ=Asia/Taipei pytest -q
OPENSPEC_TELEMETRY=0 openspec validate --all --strict --no-interactive
git diff --check
```

Normal CI/tests must remain offline and must not require Groq/Ollama.

If a migration is unexpectedly added, also run the repository SQLite migration round trip. Prefer no migration unless concrete evidence requires one.

## Non-goals

- no new learning/review/memory/proactive features;
- no scheduler redesign;
- no provider architecture rewrite;
- no vector database or new RAG system;
- no fake claim that Codex verified macOS/Groq/Ollama;
- no background jobs;
- no broad UI redesign;
- do not close Issue #55 from this implementation task alone.

## Delivery

Complete code/tests/docs first and commit the finished work. Do not spend effort creating/updating another PR or publishing GitHub-visible changes. If publication is unavailable, preserve the finished commit and report exact branch/SHA/tests/blockers.

This is one implementation task, not another multi-phase development issue. After it is reviewed and merged, the only remaining #55 work should be the actual target-Mac UAT and any concrete bug discovered by that run.