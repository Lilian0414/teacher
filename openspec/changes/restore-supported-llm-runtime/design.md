# Design: Restore a supported LLM runtime

## Context

The domain-shaped `LLMProvider` already exposes the required tasks and ordinary tests already use
`FakeLLMProvider`. The defect is the retired repository default plus an incomplete external
contract gate, not an absence of provider abstraction. This change should repair that boundary
without broadening the provider architecture.

## Decisions

### 1. Select one supported default against the whole contract

Use Groq's current official model/deprecation documentation as the source for the replacement.
The replacement is acceptable only when it can perform normal text chat and the existing JSON
response shapes for language assistance and memory work. Updating the string because a model
appears in a catalog, without checking the structured tasks, is insufficient.

The default remains configurable through `GROQ_MODEL`; users can still override it. Automatic
multi-model fallback is rejected because it would hide contract differences and increase the
surface of this P0 hotfix.

### 2. Keep external verification opt-in but complete

Ordinary CI must keep using fake providers. The live suite remains protected by both
`RUN_LIVE_API_TESTS=1` and an explicitly supplied API key, but it covers each domain method rather
than a subset. Live tests assert schema/behavior invariants and must not snapshot or log secrets or
entire provider responses.

If the execution environment has no live credentials, implementation may complete the suite and
record that live execution is unverified; it must not invent a key, weaken the tests, or claim a
successful live run.

### 3. Preserve controlled failure semantics

Provider rejection, timeout, or malformed JSON continues through the existing controlled error
boundary. The hotfix must not persist malformed language or memory output merely to make a live
test pass. Runtime state may report configuration presence, but must not call an untested model
"healthy" or "verified" without a real successful contract check.

## Risks / Trade-offs

- A supported model can be retired later. The complete opt-in contract suite provides a focused
  detection path, but it is not converted into paid ordinary CI in this change.
- Different supported models can vary in structured-output behavior. Contract assertions test
  domain invariants rather than provider wording.
- Live credentials may be unavailable to Codex. That is a verification limitation to report, not
  permission to expand scope or add secrets.

## Rollback

This change has no schema or persisted-data migration. Reverting restores the previous configured
default and test/docs state; user-supplied `GROQ_MODEL` overrides remain independent.

