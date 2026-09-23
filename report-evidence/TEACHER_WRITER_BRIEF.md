# Teacher report writer brief — 2026-09-24

Canonical implementation commit for this evidence run:
`5624e85ebb1ad4a229c63e6a9970c61231403159`

This file is the concise evidence handoff for scheduled report writers/reviewers. It summarizes only claims that are currently supported by repository-visible implementation and measured evidence collected on the target Mac. Use the detailed files under `report-evidence/experiments/` when a section needs methodology or exact numbers.

## Current Teacher status

Teacher is implemented as a local-first learning companion with a FastAPI Core, SQLite persistence, Textual terminal UI, long-term memory, learning/review flow, proactive practice, speech boundaries, and optional local embedding retrieval.

Target-Mac manual UAT on the evidence commit passed for the intended interactive flows, including normal conversation, help/hint, review interaction, incorrect-answer retry, STT, TTS, and the terminal UI path used during the final UAT session.

Quality verification on the same commit:

- Ruff: passed.
- strict mypy: passed, 124 source files.
- pytest: 406 passed, 6 skipped, 1 dependency deprecation warning.
- git diff check: passed.
- Alembic SQLite migration round trip: base -> head -> base -> head passed.
- Alembic head at the run: `20260830_0015`.

Do not turn the Starlette/httpx deprecation warning into a correctness failure; it did not fail the test suite.

## Measured Teacher latency evidence

Measured on the target Mac with the configured providers. These are observed benchmark results, not universal service-level guarantees.

| Path | n | Mean | Median | p95 | Min | Max | Success / recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| Memory lexical retrieval | 20 | 0.2 ms | 0.2 ms | 0.2 ms | 0.1 ms | 0.3 ms | 20/20 |
| Review deterministic grading | 20 | 1.0 ms | 0.8 ms | 1.2 ms | 0.8 ms | 4.0 ms | completed |
| Memory semantic retrieval, local Ollama | 20 | 28.1 ms | 28.1 ms | 32.2 ms | 23.9 ms | 34.8 ms | 20/20 |
| Conversation response | 20 | 429.1 ms | 300.0 ms | not derived | 204.0 ms | 930.6 ms | completed |
| STT, Groq Whisper | 10 | 487.4 ms | 488.1 ms | 647.4 ms | 348.0 ms | 650.9 ms | 10/10 |
| Review semantic grading, Groq | 20 | 808.2 ms | 760.2 ms | 1169.3 ms | 509.2 ms | 1336.2 ms | completed |
| TTS, ElevenLabs | 10 | 1854.3 ms | 1834.1 ms | 2028.9 ms | 1613.3 ms | 2205.8 ms | 10/10 |

Safe engineering interpretation:

- deterministic review grading and lexical retrieval stay local and are effectively immediate at this scale;
- local semantic-memory retrieval with Ollama remains in the tens-of-milliseconds range;
- Groq-backed conversation/STT/semantic-grading paths are in the hundreds-of-milliseconds range;
- external TTS is the slowest measured path, around the two-second scale in this run.

Do not fabricate a conversation p95; it was not derived from the retained aggregate values.

## Semantic-memory evidence

Target memory used in the controlled benchmark:

`Prefers studying late at night with instrumental music.`

Semantic query:

`Which environment improves concentration after sunset?`

The benchmark sanity check confirmed zero direct word overlap between the target memory and semantic query. Teacher's production `MemoryContextBuilder.select()` semantic path, using local Ollama `nomic-embed-text`, selected the intended target memory in 20/20 runs.

Measured semantic retrieval latency:

- median: 28.1 ms
- p95: 32.2 ms
- min: 23.9 ms
- max: 34.8 ms

This may support a report claim that Teacher can retrieve a relevant stored memory beyond direct keyword overlap in the controlled benchmark. Do not generalize this 20-run controlled result into a broad accuracy percentage for arbitrary user memories.

## Review-grading architecture evidence

Controlled benchmark of the same review item used `POST /v1/review/{item_id}/retry` so the repeated measurements did not create new attempts or mutate review stage/scheduling state.

Deterministic exact/canonical grading:
- median 0.8 ms
- p95 1.2 ms

Semantic grading through the configured Groq judge:
- median 760.2 ms
- p95 1169.3 ms

Safe interpretation: Teacher resolves straightforward accepted-answer matches locally, while ambiguous/semantic-equivalence cases can invoke the model-based semantic judge. This avoids paying the semantic-judge latency on every review answer.

Do not imply that the LLM owns review scheduling, stage transitions, durable persistence, or deterministic grading. Those responsibilities remain in Core.

## Speech evidence

STT benchmark:

- 10/10 successful requests.
- median 488.1 ms.
- p95 647.4 ms.
- one identical transcript across all 10 repeated submissions of the same fixed WAV:
  `I forgot to bring my umbrella yesterday.`

This is a transcription-service-path benchmark using a fixed WAV. It does not include human speaking time or microphone capture duration. Real microphone interaction was verified separately in target-Mac UAT.

TTS benchmark:

- 10/10 successful requests.
- median 1834.1 ms.
- p95 2028.9 ms.

TTS is an external-provider path and was the slowest Teacher path in the current benchmark set.

## Failure / fallback evidence

### Assistant provider fail-once + retry

Using the deterministic `fake_fail_once` provider:

- first assistant attempt failed truthfully;
- response was retryable;
- no assistant message was fabricated for the failed attempt;
- retry succeeded;
- persisted state after recovery contained exactly one user message and one assistant message.

Result: PASS.

Safe interpretation: retry recovery preserves the original user turn and does not duplicate durable conversation state in this isolated failure test.

### Embedding failure + lexical fallback

Teacher's production memory context path was configured with an intentionally unreachable embedding endpoint.

Target memory:
`Drinks black coffee before early classes.`

Query:
`black coffee`

Observed:
- embedding endpoint unavailable;
- retrieval continued through lexical/person fallback;
- target memory was still selected;
- measured fallback run latency: 42.1 ms.

Result: PASS.

Safe interpretation: semantic embedding failure can degrade to the lexical/person retrieval path rather than breaking memory retrieval entirely for a query that remains recoverable lexically.

Do not imply that arbitrary semantic queries remain recoverable when embeddings are unavailable.

## Evidence files

Detailed summaries:

- `report-evidence/experiments/conversation-latency-summary.md`
- `report-evidence/experiments/review-grading-latency-summary.md`
- `report-evidence/experiments/memory-retrieval-latency-summary.md`
- `report-evidence/experiments/stt-latency-summary.md`
- `report-evidence/experiments/tts-latency-summary.md`
- `report-evidence/experiments/teacher-latency-overview.md`
- `report-evidence/experiments/failure-fallback-summary.md`
- `report-evidence/experiments/failure-assistant-retry.json`
- `report-evidence/experiments/failure-embedding-fallback.json`

Some raw CSV files remain local and are not yet mirrored to GitHub. Writers may use the aggregate values above and the checked-in summary files, but must not invent missing raw values or additional statistics.

## Report-writing boundary

Teacher evidence in this branch is ready for report writing.

Teacher Edge is not part of this handoff yet. Do not use the unfinished Watcher -> Pi ingress benchmark or create new Teacher Edge latency claims until separate evidence is added.

When writing report prose, prefer engineering conclusions supported by the implementation and the measurements above. Keep measured conditions explicit, avoid universal performance claims, and distinguish current implementation from proposed/future extensions.
