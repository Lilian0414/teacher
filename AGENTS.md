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
- **ChatGPT/planner**: requirement clarification, repository inspection, architecture judgment, GitHub Issue/spec writing, work ordering, Codex delegation, GitHub branch/PR publication orchestration, PR review, CI/UAT judgment, and direct implementation only when the user explicitly assigns it.
- **Codex**: repository implementation, repository-native verification, commit creation, and publication of its implementation branch when the active Codex environment has a usable Git remote and push permission.

Use one active implementation writer per coherent task. Do not silently replace an assigned writer because publication, review, or CI is delayed.

## Durable task contract

Meaningful behavior, API, schema, migration, cross-module, or otherwise non-trivial changes should have a clear GitHub Issue/spec before implementation. The Issue should define scope, non-goals, acceptance criteria, constraints, and verification.

For explicitly delegated implementation work, the linked GitHub Issue/spec is the task-specific source of truth.

OpenSpec may be used when it adds useful design detail, but it must not create a second conflicting status lifecycle. Beads may remain available as optional local/internal task or memory tooling, but it is not required for the GitHub Issue → implementation → PR workflow and does not override the linked GitHub Issue/spec.

## Codex implementation handoff

For tasks explicitly delegated to Codex, use:

`inspect → confirm publication path → implement → verify → commit → publish branch when possible → report → STOP`

Before editing, Codex must:

- read the linked Issue/spec and these repository instructions;
- confirm the requested base branch/SHA;
- inspect the relevant current code, tests, migrations, and runtime boundaries;
- check whether valid equivalent implementation work already exists;
- inspect the active checkout's Git publication path, including `git remote -v`, the current branch, and whether a GitHub-visible branch can be pushed from this environment.

For an initial implementation where no PR exists yet, if there is no usable remote/push path and the task expects a durable GitHub handoff, STOP before editing and report that publication blocker unless the user explicitly permits a local-only implementation. Do not knowingly create implementation work that will exist only in a disposable sandbox when a GitHub-visible handoff is required.

During implementation:

- make the smallest coherent change that satisfies the Issue;
- preserve unrelated behavior and user changes;
- do not broaden scope or perform unrelated refactors;
- run the strongest applicable repository-native checks;
- commit completed work;
- after commit, if the active environment has a usable remote and push permission, publish the same implementation branch to GitHub before stopping;
- report the commit SHA, local branch, GitHub-visible branch/head when publication succeeds, checks actually run, and any unverified layer;
- if publication fails after a valid commit, preserve the completed work and report the exact publication blocker. Do not reimplement the task merely because publication failed.

### Codex routing: initial implementation vs PR follow-up

Choose the Codex trigger location from the current lifecycle state. Do not use the two entry modes interchangeably.

**Initial implementation (no PR exists yet):**

- trigger Codex from the GitHub Issue/spec;
- work from the explicitly requested base branch/SHA, normally `main@<sha>`;
- confirm a usable publication path before editing when a GitHub-visible handoff is expected;
- implement and verify the scoped task, commit it, publish the implementation branch when the environment permits, report the GitHub-visible branch/head, and stop;
- do **not** create the pull request itself. Once the branch is GitHub-visible, ChatGPT/planner may create the PR through the GitHub connector and continue independent review.

**PR review follow-up (a PR already exists):**

- trigger Codex from the existing PR conversation, not from the original Issue;
- treat the current PR head/branch as the implementation baseline and continue the same implementation writer/task;
- do not reset to `main`, do not reconstruct the implementation from the Issue's original base SHA, and do not create a duplicate implementation branch or PR;
- before editing, confirm the checkout contains the current PR head (or the PR context has supplied an equivalent checked-out head). If the current PR head is unavailable, STOP and report the checkout/context blocker instead of rebuilding from base;
- apply only the review-requested correction, verify it, commit it on the existing PR branch, push/publish that follow-up commit to the same GitHub-visible PR branch when the environment permits, report the new head/commit, and stop;
- if the existing PR branch cannot be updated from the active environment, report the publication blocker instead of opening another branch or recreating the task.

After a PR follow-up commit appears on GitHub, ChatGPT/planner must re-fetch the PR's current head SHA, independently review the new GitHub-visible diff, and accept CI only when the CI run corresponds to that exact current head SHA.

Hard stop rules for Codex-delegated work:

- **Do not create a pull request.**
- **Do not merge.**
- Publishing the current implementation branch is allowed and preferred when the active environment has a usable remote and push permission.
- Do not start a separate publication-recovery implementation in a fresh sandbox if the original commit is unavailable there; report that the original work is inaccessible instead of reconstructing it implicitly.
- A valid completed local implementation commit is `implementation complete (local)` even when no GitHub-visible branch exists, but it is not yet a durable GitHub handoff.
- A GitHub-visible implementation branch is the preferred handoff state before PR creation.
- A failed publication step is not an implementation correctness failure and is not a reason to reimplement valid work unless the user explicitly authorizes a new implementation.
- When review findings require code changes, return them to the same Codex implementation writer/task where practical, using the existing PR conversation once a PR exists, then verify, commit, and publish the fix to the same PR branch before stopping again.

Once Codex work is GitHub-visible, ChatGPT/planner may create the PR, independently review the exact GitHub-visible diff/head, inspect CI for that exact head, and coordinate follow-up. The user does not need to manually create the PR unless they prefer to.

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

`implementation complete (local)` → `GitHub-visible branch` → `PR available` → `current-head CI green` → `UAT passed` → `merged`

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
