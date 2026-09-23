# Failure / fallback evidence plan — 2026-09-24

Source commit: `5624e85ebb1ad4a229c63e6a9970c61231403159`

The failure/fallback evidence run intentionally uses isolated benchmark storage and deterministic failure seams. It does not modify the final-UAT database.

Planned checks:

1. **Assistant provider fail-once + retry**
   - run Core with `LLM_PROVIDER=fake_fail_once`;
   - first assistant chat call must fail with a retryable outcome rather than a fabricated success;
   - retry must succeed;
   - persistence check must show one user message and one assistant message, with no duplicated user turn.

2. **Embedding query failure + lexical fallback**
   - use Teacher's production `MemoryContextBuilder`;
   - configure an intentionally unreachable embedding endpoint;
   - verify retrieval still succeeds through lexical/person relevance for a known target memory.

Raw outputs and final PASS/FAIL results will be added after the isolated run completes.
