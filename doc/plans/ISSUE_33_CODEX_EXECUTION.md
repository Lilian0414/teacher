# Issue #33 Codex execution contract

Source: GitHub Issue #33 — Make default memory recall useful for paraphrases without blocking chat.

Base: `main` at `9857e4d8d1ce43c439ae7286b1328324aae7c913` after Issue #31 reached `main` and post-merge CI passed.

## Goal

Make long-term memory recall semantically useful for normal paraphrases while keeping the chat runtime responsive and the retrieval path read-only. Reuse the existing SQLite memory model and hybrid ranking; do not introduce a vector database, a second memory system, or an LLM-based memory judge.

The product target is the existing single-user Mac app. The selected practical semantic profile should use the already-supported OpenAI-compatible local embedding boundary (the repository currently documents Ollama / `nomic-embed-text`) and remain able to fall back to lexical/person matching when semantic infrastructure is unavailable.

## Verified current behavior

The current implementation has three coupled problems:

1. `Settings.embeddings_enabled` and `.env.example` default to `false`, so the fresh normal runtime uses only lexical/person overlap.
2. `MemoryContextBuilder.select()` is synchronous. When embeddings are enabled it calls the provider synchronously for the query and can also embed up to `embedding_backfill_limit` candidate memories inside the chat read path.
3. Query-time lazy backfill persists each newly generated candidate vector through `MemoryRepository.set_embedding()`, which commits per candidate.

The provider itself uses synchronous `httpx.Client`, so this work occurs directly inside the async conversation request. `ConversationService._generate_assistant_reply()` calls `memory_context_builder.build(...)` synchronously before the LLM chat request.

Memory writes have the same sync-I/O problem: `MemoryService.remember()` and conversation-end extraction eventually call `_embed()` synchronously even though the public service methods are async.

The existing useful pieces should be preserved:

- active/deleted memory status and deleted exclusion;
- person canonical-name / alias relevance;
- English token and Chinese bigram lexical relevance;
- bounded candidate set (currently up to 200) and context result limit (up to 5);
- cosine semantic ranking only for compatible model/dimension vectors;
- SQLite JSON vector persistence;
- lexical fallback when embeddings fail;
- Issue #32 atomic memory extraction semantics.

## Architecture decision

Use the existing embedding approach, but move it behind a genuinely asynchronous, batch-capable boundary.

The intended shape is:

`memory write / extraction`
→ async embedding request (batch when multiple contents are known)
→ deterministic persistence with model + dimension metadata

and:

`chat query`
→ bounded active-memory read
→ one async query embedding
→ compare only already-persisted compatible vectors
→ hybrid rank in Python
→ inject at most the configured memory limit

The chat read path must not create/backfill/update embeddings.

Do not add pgvector, Chroma, Pinecone, FAISS, LangChain, Mem0, Letta, or another retrieval store for this issue.

## Required behavior

### 1. Make the embedding provider async and batch-capable

Replace the synchronous provider boundary with an async API suitable for FastAPI runtime use.

A small protocol such as `await embed(text)` plus `await embed_many(texts)`, or a single batch-first method, is acceptable. Prefer one provider request for multiple texts when the upstream OpenAI-compatible endpoint supports list input.

`OpenAIEmbeddingProvider` must use async HTTP I/O (`httpx.AsyncClient` or equivalent). A slow embedding request may delay the request that needs semantic recall, but it must not block the Core event loop or unrelated async work.

Preserve explicit `model` and `dimensions` identity. Provider output must still be normalized/validated and dimension mismatches must fail safely.

No external embedding API may be called by the normal test suite.

### 2. Make memory recall awaitable without hiding writes

Make `MemoryContextBuilder.select()` / `build()` awaitable as needed and update `ConversationService` to await memory context construction.

For each recall:

- read at most the configured bounded candidate limit;
- read active memories only;
- generate at most one query embedding request;
- use only stored vectors whose model and dimensions match the configured provider;
- perform hybrid lexical/person + cosine ranking in Python;
- return at most the configured context limit;
- perform **zero DB writes / zero commits** from the retrieval path.

If query embedding fails, times out, is malformed, or has the wrong dimension, recall must continue using lexical/person signals.

If a candidate has no compatible stored vector, it remains eligible for lexical/person matching only. Do not lazily embed it during the chat request.

### 3. Move vector generation to write-time / explicit batch work

When a user explicitly remembers something, compute its embedding asynchronously before the synchronous persistence mutation.

When conversation-end extraction produces multiple valid candidate contents, batch embedding work where practical rather than making one network call per candidate. Embedding failure is optional metadata failure: the memory extraction result must remain truthful and the durable memory transaction must preserve the atomicity / rollback behavior established by Issue #32.

Do not commit partial memory extraction merely because some vectors succeeded.

Content updates that fail to obtain a replacement vector must not retain a stale vector for old content.

### 4. Remove query-time lazy backfill

The current `MemoryContextBuilder` lazy re-embedding/backfill loop and per-memory `set_embedding(...); commit()` behavior must disappear from chat retrieval.

If old-vector backfill support is retained, it must be an explicit maintenance/write boundary and must batch persistence sensibly. Do not create a hidden background system unless clearly necessary.

If no explicit backfill command is added in this issue, remove or repurpose `EMBEDDING_BACKFILL_LIMIT` so the runtime/docs do not claim that query-time lazy backfill still exists. Older/incompatible rows may safely remain lexical-only until they are rewritten or explicitly backfilled.

### 5. Make the practical semantic setup obvious

The primary documented Mac setup must make semantic recall usable without requiring the user to discover an undocumented flag.

Use the existing local OpenAI-compatible embedding profile unless there is a strong repository-level reason not to:

- local endpoint such as Ollama;
- `nomic-embed-text`;
- explicit model and exact dimension configuration;
- lexical fallback when unavailable.

A reasonable implementation is to make the recommended `.env.example` semantic profile enabled and document the one-time local model/server setup, while keeping a clear `EMBEDDINGS_ENABLED=false` opt-out. It is acceptable to keep the `Settings` class's bare-code default conservative if that prevents accidental network calls in tests or environments that do not use `.env`; the **fresh documented product path** must nevertheless be semantic by default once its documented local dependency is installed.

Do not add a heavyweight Python embedding/model dependency merely to avoid the existing local provider boundary.

Update README / memory documentation so they no longer describe synchronous providers or query-time lazy backfill.

### 6. Preserve ranking safety and scope

Preserve:

- active/deleted filtering;
- person name/alias relevance;
- lexical fallback;
- result bound;
- compatible model/dimension checks;
- confidence wording in injected memory context.

Do not change memory extraction policy, memory categories, soft-delete semantics, conflict/update allowlists, or learning/proactive behavior in this issue.

## Acceptance tests

Add deterministic tests proving at least the following.

### Semantic conversation integration

Store a memory with semantic vector metadata, then send a later conversation query with **true zero lexical-token overlap**, for example:

- memory: `My favorite meal is salmon.`
- later query: `What food do I like best?`

The memory must appear in the system memory context seen by the chat provider (or equivalent observable conversation-context boundary). This must exercise the real conversation + memory context wiring, not only call `hybrid_relevance_score()` directly.

### Deleted / unrelated exclusion

A deleted semantic match is never injected. An unrelated memory with a low semantic score remains excluded. Existing person relevance behavior remains covered.

### Async non-blocking behavior

Use a deterministic async embedding fake that deliberately waits on an `asyncio.Event` or similar. While one memory recall is waiting for the embedding result, another unrelated async coroutine/request must be able to make progress before the embedding is released. The test must fail if the provider boundary becomes a blocking synchronous call.

### Read-only query path

Prove that query-time recall does not call `set_embedding`, does not commit vectors, and does not mutate missing/incompatible candidate vectors. The candidate DB read remains bounded.

### Batch/write behavior

Cover write-time embedding persistence and failure fallback. If multiple extraction candidates are embedded, prove the provider is not called once per candidate when batching is implemented.

### Compatibility/fallback

- wrong model vector is ignored semantically;
- wrong dimension vector is ignored semantically;
- query embedding failure falls back to lexical/person matching;
- write embedding failure still stores the truthful memory without semantic metadata;
- updated content does not keep a stale old-content vector after replacement embedding failure.

### Configuration/docs

Runtime factory tests should verify the selected documented embedding configuration and aliases. Normal CI must remain fully offline.

## Likely touch points

- `src/companion/providers/embeddings.py`
- `src/companion/memory/context.py`
- `src/companion/memory/service.py`
- `src/companion/memory/repository.py` only as needed to remove query writes / support batched persistence
- `src/companion/conversation/service.py`
- `src/companion/api/dependencies.py`
- `src/companion/settings.py` only if the selected setup semantics require it
- `.env.example`
- `README.md`
- `doc/M2_MEMORY.md`
- `tests/unit/test_memory.py`
- `tests/unit/test_embedding_provider.py`
- `tests/integration/test_embedding_runtime.py`
- a focused conversation-memory integration test

A DB migration should not be necessary because memory vectors already store model + dimensions. Do not add one unless concrete implementation evidence requires it.

## Explicit non-goals

- No vector database or approximate nearest-neighbor index.
- No new memory schema/model unless unavoidable.
- No LLM query-rewrite / LLM memory relevance judge.
- No new learning-item or proactive behavior.
- No `/say` reliability work (#34).
- No broad async rewrite of unrelated repositories/services.
- No background daemon/job framework.
- No cloud embedding vendor requirement for ordinary tests.

## Required verification

Run and report:

- `ruff check .`
- strict `mypy`
- full `pytest`
- focused memory / embedding / conversation-context tests
- `git diff --check`
- migration round trip only if a migration is actually added

The full test suite must perform no real Groq or embedding network request.

## Delivery / duplicate-run guard

- Use one active Codex implementation task for Issue #33 by default.
- Implement production code/tests on a dedicated child branch from `spec/issue-33-async-semantic-memory` when publication controls allow it.
- Target the planning branch with a child PR if possible; do not merge.
- ChatGPT owns the complete GitHub-visible diff review, CI verification, focused review fixes, and merge.
- If publication is blocked, preserve the same completed task/commit and use Push/Create PR handoff later. Do not redo implementation just because publishing failed.
- Do not broaden into Issue #34 or unrelated cleanup.
