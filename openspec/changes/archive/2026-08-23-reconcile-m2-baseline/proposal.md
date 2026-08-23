# Change: Reconcile the M2 baseline

## Why

The repository's implementation and tests describe a small, working M2, but the Markdown documents still contain older and contradictory plans. Examples include listing memory extraction as both implemented and unimplemented, retaining the removed `/explain` command, referring to a non-existent `docs/` layout, and claiming unimplemented private/audit/candidate workflows.

This drift makes later Codex work unsafe because an agent cannot tell which source is authoritative.

## What Changes

- Establish one OpenSpec baseline for the behavior already implemented through M2.
- Align README and the concise project documents with tested behavior.
- Remove obsolete `/explain`, `docs/`, 20-memory, private-mode, audit-log, candidate-approval, and `/memory` claims from the completed baseline.
- Record unimplemented capabilities as future work instead of silently promising them.
- Remove the legacy monolithic technical specification after its valid constraints are represented by OpenSpec and concise project documents.

## Non-goals

- No application behavior changes.
- No database migration.
- No M3 learning/review implementation.
- No proactive scheduling, voice, Raspberry Pi, webcam, or file tools.
- No live Groq API call.

## Measurable Outcome

A developer or agent can read OpenSpec, README, and the concise project documents without finding contradictory M0–M2 commands, paths, limits, or completion claims. Ruff, mypy, and the existing pytest suite remain green.
