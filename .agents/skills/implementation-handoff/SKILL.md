---
name: implementation-handoff
description: Implement an already-scoped repository task, verify it with repository-native evidence, commit the completed work, and hand it back for human PR publication. Use for tasks explicitly delegated to Codex after the Issue/spec and hard constraints are defined. Preserve scope, avoid duplicate writers, report the commit/task state and checks, do not create a PR, and do not merge.
metadata:
  version: "3.0.0"
---

# Implementation Handoff

Use this skill only for implementation explicitly delegated to Codex after a task is sufficiently specified. Planning, PR publication, PR review, CI acceptance, UAT, and merge belong outside this skill.

## 1. Resolve authoritative inputs

Before editing:

- read the current linked GitHub Issue/spec or execution contract;
- read repository-local `AGENTS.md` and relevant directory instructions;
- confirm the requested base branch or base SHA;
- check whether equivalent valid implementation work already exists and can be reused.

The linked GitHub Issue/spec is the task-specific source of truth. Optional OpenSpec or Beads context may supplement it but must not override or duplicate the active task contract.

If instructions conflict in a way that changes scope, safety, data, migrations, or compatibility, surface the conflict instead of guessing.

## 2. Inspect before changing code

Reconstruct the relevant current behavior from repository evidence.

Do not implement from assumptions based only on filenames, class names, README prose, TODOs, or isolated snippets. Inspect enough code, tests, migrations, and runtime boundaries to understand the behavior being changed.

## 3. Implement the smallest coherent change

- Implement only what the acceptance criteria require plus necessary supporting changes.
- Preserve unrelated behavior and user changes.
- Reuse repository conventions and existing abstractions unless the task explicitly requires changing them.
- Do not silently add unrelated refactors, dependencies, migrations, redesigns, or cleanup.
- Keep one active implementation writer per coherent task.

If valid implementation for the same task already exists, reuse or continue it rather than starting a duplicate implementation run.

## 4. Verify with repository-native evidence

Run the strongest applicable checks required by the repository and Issue, such as:

- focused tests for the changed behavior;
- `ruff check .`;
- strict `mypy .`;
- `pytest`;
- build/package checks when relevant;
- migration upgrade/downgrade or round-trip checks when relevant;
- `git diff --check`;
- behavior-level/manual verification when automated tests do not prove the requested outcome.

Do not claim a layer passed if it was not run. If a required verification layer cannot run in the environment, report it explicitly as unverified.

## 5. Commit and hand off

When implementation and applicable verification are complete:

1. create a coherent commit or commit series;
2. preserve the resulting branch/task state;
3. report:
   - commit SHA;
   - branch/task ref when available;
   - concise changed behavior/files;
   - checks actually run and results;
   - any remaining risk or unverified layer;
4. stop.

## Hard stop rules

- **Do not create a pull request.**
- **Do not attempt PR publication or PR UI recovery.**
- **Do not merge.**
- Do not rerun valid implementation merely because a PR does not exist yet.
- Publication is a separate user-controlled step after handoff unless the user explicitly changes ownership.

A completed, verified implementation commit is `implementation complete` even when no PR exists yet. Keep later states distinct: `PR available` → `current-head CI green` → `UAT passed` → `merged`.
