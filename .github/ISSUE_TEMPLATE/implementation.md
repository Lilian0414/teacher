---
name: Implementation change
description: Scope a meaningful Teacher behavior, API, schema, migration, or cross-module change before implementation.
title: ""
labels: []
assignees: []
---

## Context / evidence

Describe the observed behavior, user report, reproduction, code evidence, or prior decision that motivates this change. Prefer repository/runtime evidence over assumptions.

## Problem

What is wrong, missing, inconsistent, or worth improving?

## Goal

What outcome should this change produce?

## Scope

What is intentionally included in this task?

## Non-goals

What adjacent work is intentionally excluded?

## Expected behavior

Describe the observable behavior after the change, including important failure or boundary behavior when relevant.

## Acceptance criteria

- [ ] The requested core behavior works as described.
- [ ] Existing behavior outside the agreed scope is preserved.
- [ ] Relevant regression and repository-native quality checks pass.
- [ ] User-facing behavior is manually or integration-verified when automated tests are insufficient.

Add task-specific criteria below:

- [ ] 

## Architecture / constraints

Record boundaries that implementation must preserve, such as canonical state ownership, API compatibility, migration/data-safety rules, performance limits, dependency constraints, or explicit areas that must not change. Write `None` when there are no material constraints.

## Verification

State how completion will be proven. Use only checks that apply to this change, for example:

- focused tests for the changed behavior;
- `ruff check .`;
- strict `mypy .`;
- `pytest`;
- migration upgrade/downgrade or round-trip checks;
- `git diff --check`;
- UI/manual flow verification;
- production smoke test when deployment is part of the task.

## Dependencies / related work

Link blocking Issues, related PRs, OpenSpec artifacts, or prior decisions when they materially affect this task. Write `None` when not applicable.

## Implementation handoff

When delegating this Issue to Codex, provide the requested base branch/SHA and use the repository contract:

`inspect → implement → verify → commit → report → STOP`

Codex must not create a PR, attempt PR publication recovery, or merge. The user publishes Codex work manually unless ownership is explicitly changed.
