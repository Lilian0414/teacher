---
name: implementation-handoff
description: Implement an already-scoped repository task, verify it with repository-native evidence, commit the completed work, and hand it back for human PR publication or continued review. Use for tasks explicitly delegated to Codex after the Issue/spec and hard constraints are defined. Preserve scope, avoid duplicate writers, report the commit/task state and checks, do not create a new PR, and do not merge.
metadata:
  version: "3.1.0"
---

# Implementation Handoff

Use this skill only for implementation explicitly delegated to Codex after a task is sufficiently specified. Planning, PR creation/publication, PR review judgment, CI acceptance, UAT, and merge belong outside this skill.

This skill has two entry modes. Choose the mode from the current repository lifecycle state; do not use them interchangeably.

- **Initial implementation:** no PR exists yet. Enter from the GitHub Issue/spec and the explicitly requested base branch/SHA.
- **Existing-PR follow-up:** a PR already exists and review requires code changes. Enter from that PR conversation and continue from the current PR head/branch.

## 1. Resolve authoritative inputs

Before editing, always:

- read repository-local `AGENTS.md` and relevant directory instructions;
- read the current task contract;
- inspect enough repository evidence to understand the requested behavior;
- check whether equivalent valid implementation work already exists and can be reused.

### Initial implementation mode

- Read the linked GitHub Issue/spec or execution contract.
- Confirm the explicitly requested base branch or base SHA, normally `main@<sha>`.
- Treat the linked Issue/spec as the task-specific source of truth.

### Existing-PR follow-up mode

- Read the existing PR conversation, review finding, and linked Issue/spec for scope context.
- Treat the **current PR head/branch** as the implementation baseline. The original Issue base SHA is no longer the checkout target.
- Confirm that the checkout contains the current PR head, or that the PR context has supplied an equivalent checked-out head.
- Do not reset to `main`, reconstruct the implementation from the Issue's original base, create a duplicate implementation branch, or open another PR.
- If the current PR head is unavailable in the environment, STOP and report the exact checkout/context blocker. Do not rebuild the existing implementation from base merely to continue.

Optional OpenSpec or Beads context may supplement the task contract but must not override or duplicate the active Issue/PR contract.

If instructions conflict in a way that changes scope, safety, data, migrations, or compatibility, surface the conflict instead of guessing.

## 2. Inspect before changing code

Reconstruct the relevant current behavior from repository evidence.

Do not implement from assumptions based only on filenames, class names, README prose, TODOs, or isolated snippets. Inspect enough code, tests, migrations, runtime boundaries, and—when in existing-PR follow-up mode—the current PR diff/head state to understand the behavior being changed.

## 3. Implement the smallest coherent change

- Implement only what the acceptance criteria or current PR review finding require, plus necessary supporting changes.
- Preserve unrelated behavior and user changes.
- Reuse repository conventions and existing abstractions unless the task explicitly requires changing them.
- Do not silently add unrelated refactors, dependencies, migrations, redesigns, or cleanup.
- Keep one active implementation writer per coherent task.

If valid implementation for the same task already exists, reuse or continue it rather than starting a duplicate implementation run.

For an existing-PR follow-up, modify only the existing PR implementation necessary to resolve the review finding. Preserve the rest of the PR unless the finding proves another change is required.

## 4. Verify with repository-native evidence

Run the strongest applicable checks required by the repository and Issue/PR review, such as:

- focused tests for the changed behavior;
- `ruff check .`;
- strict `mypy .`;
- `pytest`;
- build/package checks when relevant;
- migration upgrade/downgrade or round-trip checks when relevant;
- `git diff --check`;
- behavior-level/manual verification when automated tests do not prove the requested outcome.

Do not claim a layer passed if it was not run. If a required verification layer cannot run in the environment, report it explicitly as unverified.

For an existing-PR follow-up, explicitly report the PR head/branch you continued from and the resulting new commit/head so the reviewer can verify that subsequent CI belongs to the updated PR head.

## 5. Commit and hand off

When implementation and applicable verification are complete:

1. create a coherent commit or commit series;
2. preserve the resulting branch/task state;
3. report:
   - commit SHA;
   - branch/task ref when available;
   - for PR follow-up, the existing PR number and prior/current head when available;
   - concise changed behavior/files;
   - checks actually run and results;
   - any remaining risk or unverified layer;
4. stop.

## Hard stop rules

- **Do not create a new pull request.**
- **Do not attempt PR creation/publication or PR UI recovery.**
- **Do not merge.**
- In initial implementation mode, do not rerun valid implementation merely because a PR does not exist yet.
- In existing-PR follow-up mode, updating/committing to the already-existing PR branch is continuation of the same implementation; it is not permission to create another PR.
- If the existing PR head cannot be accessed, stop and report the blocker rather than starting over from `main`.

A completed, verified initial implementation commit is `implementation complete` even when no PR exists yet. Keep later states distinct: `PR available` → `current-head CI green` → `UAT passed` → `merged`.

After a PR follow-up commit is available, the external reviewer must re-fetch the PR's new head, independently review the GitHub-visible diff, and accept CI only when the run belongs to that exact current head SHA.
