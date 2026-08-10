# Design: Reconcile the M2 baseline

## Context

This is a retrospective documentation reconciliation. Commit `09559f9` already passed Ruff, strict mypy, and 69 tests with 4 skips. The code and tests therefore provide stronger evidence of shipped behavior than older forward-looking Markdown.

## Decisions

### 1. Tested behavior defines the completed baseline

The baseline will describe only behavior supported by current code and tests:

- deterministic availability commands;
- persisted English text conversations;
- `/help`, `/hint`, and `/say`;
- active/deleted long-term memories;
- `/remember`, `/memories`, and confirmed `/forget`;
- conversation-end extraction from user messages;
- deterministic rejection of invalid sources, trivial greetings, and exact duplicates;
- at most five relevant memories injected into chat.

### 2. Keep the existing `doc/` directory for legacy milestone summaries

Renaming directories would add noise without improving the running system. References will use the actual `doc/` paths. New authoritative requirements live under `openspec/specs/` after archive.

### 3. Remove, do not preserve, the monolithic legacy specification

`doc/AI_Learning_Companion_Technical_Spec.md` mixes future aspirations with completed requirements and duplicates milestone files. Git history preserves it if needed. Keeping it active would recreate the same ambiguity OpenSpec is intended to solve.

### 4. Explicitly defer advanced memory governance

Private conversations, sensitivity levels, candidate approval, audit history, conflict states, memory editing, and proactive-use permissions are not part of completed M2. They may return through a future approved OpenSpec change.

### 5. No production-code edits

If reconciliation uncovers an implementation defect rather than a documentation mismatch, Codex must create a follow-up Bead and stop expanding this change.

## Risks

- Removing old promises could look like lost scope. Mitigation: future-facing features remain visible in the project roadmap/non-goals, but are not labeled completed.
- Documentation may drift again. Mitigation: later milestones begin with OpenSpec and tasks must reference requirements.
