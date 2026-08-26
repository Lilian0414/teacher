# Issue #33 reopened acceptance-fix contract

Source: reopened GitHub Issue #33 — Make default memory recall useful for paraphrases without blocking chat.

Base: `main` at `a26375717d9f7626715806e9f4748eb8c1a00619`.

## Why Issue #33 was reopened

PR #45 correctly made semantic recall async, bounded, read-only at query time, model/dimension-safe, and covered true zero-token-overlap retrieval. Final E2E acceptance audit found the last original criterion is still false for a fresh documented setup.

Verified mismatch on current `main`:

- `Settings.embeddings_enabled` defaults to `False`.
- `.env.example` defines `EMBEDDINGS_ENABLED=true` and the Ollama semantic profile.
- README says the documented local semantic profile is enabled by default.
- The fresh-clone setup runs venv/install/Alembic/`companion` but never copies `.env.example` to `.env` or otherwise activates that profile.
- `companion.cli.local()` simply loads environment-backed settings and launches Core/UI; it does not materialize `.env.example`.

Therefore following the README literally launches lexical-only memory recall, so the fresh documented setup cannot satisfy the paraphrase outcome from Issue #33.

## Goal

Make the fresh documented Mac setup truthfully and reproducibly activate the existing local semantic profile while preserving safe code defaults for tests/offline environments.

Do not redesign memory retrieval.

## Required approach

Keep the programmatic `Settings.embeddings_enabled=False` default unless there is strong evidence that changing it cannot cause unexpected Ollama network waits in tests or no-config runtimes. The preferred fix is to make the **documented setup profile explicit and executable**.

At minimum:

1. Fresh-clone instructions must create `.env` from `.env.example` before first `companion` run, with an explicit step to fill `GROQ_API_KEY`.
2. The same setup path must tell the user to install/start Ollama and pull the documented embedding model before relying on semantic recall.
3. Wording must stop implying that a bare `Settings()` / no-env launch has embeddings enabled. Say that the documented `.env.example` local profile enables semantic recall, while `EMBEDDINGS_ENABLED=false` is the lexical-only opt-out.
4. Keep `.env.example` authoritative and aligned with Settings fields/model/dimensions.
5. Add a deterministic configuration/setup regression test that proves the checked-in `.env.example` profile loads with embeddings enabled and the expected base URL/model/dimensions, without making a network call.
6. If a packaging/startup test can cheaply prove the documented environment is discoverable from the supported launch workflow, add it; do not build a general installer/doctor command for this issue.

## Acceptance tests

- Loading Settings against the checked-in `.env.example` (or an exact temporary copy) yields `embeddings_enabled=True`, `embedding_base_url=http://127.0.0.1:11434/v1`, model `nomic-embed-text`, dimensions `768`, and the documented timeout.
- The test makes no Ollama/Groq request.
- Existing ordinary tests remain lexical/offline unless they explicitly opt into embeddings.
- README fresh-clone sequence includes creating `.env`, setting the Groq key, preparing Ollama/model, Alembic, then running `companion` in an order that can actually work.
- Existing async semantic-memory integration tests remain unchanged/green.

## Likely touch points

- `README.md`
- `.env.example` only if alignment changes are needed
- `tests/packaging/` or `tests/unit/test_settings.py`
- `src/companion/settings.py` only if a tiny testability/alignment change is needed; avoid changing safe default behavior casually

## Non-goals

- No retrieval algorithm changes.
- No vector DB.
- No embedding provider rewrite.
- No query-time backfill.
- No automatic Homebrew/Ollama installation.
- No general setup wizard.

## Required verification

Run and report:

- focused settings/packaging test;
- existing semantic memory integration tests;
- `ruff check .`;
- strict `mypy`;
- full `pytest`;
- `git diff --check`.

No migration is expected.

## Delivery guard

This is one focused Codex acceptance-fix run for reopened Issue #33. Do not merge. Preserve the exact task/commit if publication is blocked; ChatGPT owns GitHub-visible review, CI, focused fixes, and merge.