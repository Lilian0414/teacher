# Agent Instructions

These instructions define the repository-local development workflow for Teacher.

## Precedence

Follow, in order:

1. Explicit current user/task instructions.
2. This repository's `AGENTS.md` and more specific directory instructions.
3. The linked GitHub Issue/spec and repository-native quality gates.
4. Optional local tooling such as OpenSpec or Beads when it helps without creating a conflicting workflow.

When behavior or requirements are unclear, inspect repository evidence first. Do not implement from assumptions based only on filenames, README prose, TODOs, or isolated snippets.

## Ownership

Default ownership is:

- **User**: product direction and final decisions.
- **ChatGPT/planner**: requirement clarification, repository inspection, architecture judgment, GitHub Issue/spec writing, work ordering, Codex delegation, PR review, CI/UAT judgment, and direct implementation only when the user explicitly assigns it.
- **Codex**: repository implementation, repository-native verification, and commit creation for tasks explicitly delegated to Codex.

Use one active implementation writer per coherent task. Do not silently replace an assigned writer because publication, review, or CI is delayed.

## Durable task contract

Meaningful behavior, API, schema, migration, cross-module, or otherwise non-trivial changes should have a clear GitHub Issue/spec before implementation. The Issue should define scope, non-goals, acceptance criteria, constraints, and verification.

For explicitly delegated implementation work, the linked GitHub Issue/spec is the task-specific source of truth.

OpenSpec may be used when it adds useful design detail, but it must not create a second conflicting status lifecycle. Beads may remain available as optional local/internal task or memory tooling, but it is not required for the GitHub Issue → implementation → PR workflow and does not override the linked GitHub Issue/spec.

## Codex implementation handoff

For tasks explicitly delegated to Codex, use:

`inspect → implement → verify → commit → report → STOP`

Before editing, Codex must:

- read the linked Issue/spec and these repository instructions;
- confirm the requested base branch/SHA;
- inspect the relevant current code, tests, migrations, and runtime boundaries;
- check whether valid equivalent implementation work already exists.

During implementation:

- make the smallest coherent change that satisfies the Issue;
- preserve unrelated behavior and user changes;
- do not broaden scope or perform unrelated refactors;
- run the strongest applicable repository-native checks;
- commit completed work and report the commit SHA, branch/task ref when available, checks actually run, and any unverified layer.

### Codex routing: initial implementation vs PR follow-up

Choose the Codex trigger location from the current lifecycle state. Do not use the two entry modes interchangeably.

**Initial implementation (no PR exists yet):**

- trigger Codex from the GitHub Issue/spec;
- work from the explicitly requested base branch/SHA, normally `main@<sha>`;
- implement and verify the scoped task, commit it, report, and stop;
- the user publishes that completed implementation as a PR.

**PR review follow-up (a PR already exists):**

- trigger Codex from the existing PR conversation, not from the original Issue;
- treat the current PR head/branch as the implementation baseline and continue the same implementation writer/task;
- do not reset to `main`, do not reconstruct the implementation from the Issue's original base SHA, and do not create a duplicate implementation branch or PR;
- before editing, confirm the checkout contains the current PR head (or the PR context has supplied an equivalent checked-out head). If the current PR head is unavailable, STOP and report the checkout/context blocker instead of rebuilding from base;
- apply only the review-requested correction, verify it, commit it on the existing PR branch, report the new head/commit, and stop.

After a PR follow-up commit appears, ChatGPT/planner must re-fetch the PR's current head SHA, independently review the new GitHub-visible diff, and accept CI only when the CI run corresponds to that exact current head SHA.

Hard stop rules for Codex-delegated work:

- **Do not create a pull request.**
- **Do not attempt PR publication or publication recovery.**
- **Do not merge.**
- A valid completed implementation commit is `implementation complete` even when no PR exists yet.
- A missing or failed PR publication step is not an implementation failure and is not a reason to reimplement valid work.
- When review findings require code changes, return them to the same Codex implementation writer/task where practical, using the existing PR conversation once a PR exists, then verify and commit the fix before stopping again.

The user publishes Codex work as a PR manually unless they explicitly change that workflow. Updating the already-existing PR branch during a PR review follow-up is continuation of the same implementation, not creation/publication of a new PR.

## ChatGPT direct implementation

When the user explicitly assigns repository implementation directly to ChatGPT instead of Codex, ChatGPT may own the full repository change lifecycle for that task:

`inspect/spec → implement → verify → commit/branch → create PR → independently review GitHub-visible diff/current head/CI → merge when acceptable and authorized`

For direct ChatGPT implementation:

- keep the same Issue/scope/verification discipline;
- create a branch rather than editing `main` directly for meaningful changes;
- independently review the resulting GitHub-visible diff rather than relying on the implementation summary;
- confirm CI/review status corresponds to the current PR head SHA before treating CI as green;
- merge only after the applicable review/CI/UAT gates are satisfied or the user explicitly accepts any remaining risk.

## PR review and completion states

After a PR exists, review correctness, scope, architecture, regression risk, migration/data safety when relevant, acceptance criteria, review comments, and current-head CI.

If PR review finds a code issue in Codex-owned work, route the follow-up from the existing PR conversation and current PR head. Do not re-trigger the original Issue from its old base SHA.

Always distinguish these states:

`implementation complete` → `PR available` → `current-head CI green` → `UAT passed` → `merged`

Do not collapse them into a generic "done" state.

## Repository-native verification

Discover and run the checks appropriate to the change. The repository currently uses Python 3.12 with these primary quality gates:

```bash
ruff check .
mypy .
pytest
git diff --check
```

Also run migration, packaging, integration, UI, or manual user-flow verification when the changed behavior requires it. Do not equate passing unit tests with proving user-facing behavior when those are different claims.

If a verification layer cannot run in the current environment, report exactly what remains unverified.

## Scope discipline

- Do not silently add unrelated refactors, dependencies, migrations, redesigns, or cleanup.
- Include newly discovered work only when it is required to satisfy or unblock the current acceptance criteria.
- Record useful but independent findings as separate follow-up work.
- Reuse existing matching branches, commits, Issues, tasks, or PRs instead of creating duplicate implementation.

## Non-interactive shell commands

Use non-interactive forms for commands that may prompt in automated environments, for example:

```bash
cp -f source dest
mv -f source dest
rm -f file
rm -rf directory
cp -rf source dest
```

If a required command, sync, push, or publication step is blocked, preserve valid completed work and report the exact blocker instead of starting over.
