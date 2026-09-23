# Failure / fallback summary — 2026-09-24

Source commit: `5624e85ebb1ad4a229c63e6a9970c61231403159`

## 1. Assistant provider fail-once + retry

Teacher was run with the deterministic `fake_fail_once` provider.

Observed behavior:

- first assistant call failed truthfully;
- response was marked retryable;
- no assistant message was fabricated for the failed attempt;
- retry succeeded;
- persisted message counts after recovery were exactly one user message and one assistant message.

Result: **PASS**

Supporting raw evidence:

`failure-assistant-retry.json`

## 2. Embedding query failure + lexical fallback

Teacher's production `MemoryContextBuilder` was configured with an intentionally unreachable embedding endpoint.

Target memory:

`Drinks black coffee before early classes.`

Query:

`black coffee`

Observed behavior:

- embedding endpoint unavailable;
- retrieval continued through lexical/person fallback;
- target memory was still selected;
- measured fallback retrieval latency: 42.1 ms.

Result: **PASS**

Supporting raw evidence:

`failure-embedding-fallback.json`

## Interpretation

These checks show that optional/external capabilities fail in a controlled way rather than corrupting durable learning state or disabling the entire recall path.

- assistant-provider failure preserves the user turn and allows a clean retry without duplicate persistence;
- embedding failure degrades to lexical/person recall instead of breaking memory retrieval.

These are isolated benchmark failure checks and do not replace the separate target-Mac UAT.
