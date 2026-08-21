---
name: solo-dev-workflow
description: Coordinate solo software-development work from idea through implementation, review, merge, and release without unnecessary process. Use when the user asks to continue, change, fix, review, or ship a code project. Classify work by size, preserve scope, reuse repo-native workflows such as OpenSpec when present, and verify real user flows before calling work done. Do not use for pure explanation or research with no intent to change a repository.
metadata:
  author: Lilian0414
  version: "0.1.0"
---

# Solo Dev Workflow

Use this skill as a lightweight orchestration layer for personal software projects. The goal is consistency and recoverability, not bureaucracy.

## Core principle

The user states what they want in ordinary language. You decide the lightest safe workflow that fits the change.

Do not force every request through an Issue or a long planning phase. Small changes should stay small. Meaningful or risky changes should leave enough durable context that another agent can continue later.

## Precedence

Before applying this skill, inspect the repository for its own instructions and workflows.

Follow this order:

1. Explicit instructions from the user.
2. Repository-specific instructions such as `AGENTS.md`, contribution docs, CI rules, and local skills.
3. Existing planning systems already used by the repository, such as OpenSpec.
4. The defaults in this skill.

Never replace a working repo-native process with a parallel one just because this skill exists.

## Restore context first

When the user says things like "continue", "keep going", or refers to prior project work:

1. Inspect the current branch, recent commits, open PRs, open Issues, and relevant project docs.
2. Check for active change/spec systems such as `openspec/` and `.agents/skills/`.
3. Reconstruct the current state before asking the user to repeat information.
4. Reuse an existing branch, Issue, or PR when it already represents the requested work.

Do not create duplicate work merely because the current chat lacks context.

## Classify the work

Choose one path.

### A. Quick change

Use for clear, localized, low-risk edits such as copy, styling, a small bug fix, or a narrow configuration adjustment.

- Do not create an Issue unless it adds real value.
- Make the smallest coherent change.
- Run the relevant verification.
- If working remotely against a shared/default branch, prefer a short-lived branch rather than editing `main` directly.

### B. Scoped change

Use for a meaningful feature, non-trivial bug, behavior change, schema/API change, or work likely to span multiple files or sessions.

- Define the goal, expected behavior, non-goals, and verification before implementation.
- If the repo already uses OpenSpec, use its existing proposal/apply workflow instead of creating duplicate planning artifacts.
- Otherwise use one Issue for one coherent change, then one branch and one PR.
- Keep implementation inside the agreed scope.

### C. Large or unclear change

Use when requirements are still moving, architecture is uncertain, or the request contains several separable features.

- Explore before implementing.
- Read the codebase and identify constraints and options.
- Do not write application code while the user explicitly says to only discuss or explore.
- Split the work into independent scoped changes once the direction is stable.
- Prefer incremental PRs over one giant PR.

See `references/decision-guide.md` for examples and edge cases.

## User intent shortcuts

Interpret common phrases consistently:

- "先討論" / "先不要動" -> explore only; read if useful, but do not implement.
- "就這樣" -> treat the current direction as stable enough to formalize if the change needs it.
- "整理成 issue" -> create or prepare the task specification; do not implement unless also asked.
- "開始做" -> classify the work, reuse existing artifacts, then implement.
- "幫我檢查" -> review the diff and behavior against the requested outcome; run relevant checks.
- "可以合併" / "合併" -> perform pre-merge verification, then merge only if authorized and checks are acceptable.
- "部署" -> deploy if the project has a deployment path, then perform a production smoke test.
- "這個之後再做" -> record as backlog/new work instead of expanding the current scope.

## Scope discipline

- Do not silently add unrelated refactors, dependencies, migrations, redesigns, or cleanup.
- If a newly discovered problem blocks the current task, explain it and fix only what is necessary to unblock the task.
- If a newly discovered problem is useful but not blocking, record it separately rather than expanding the current PR.
- Preserve unrelated user changes in a dirty worktree.
- Prefer the smallest change that fully satisfies the requested behavior.

## Git and PR defaults

For scoped changes:

- One coherent change -> one branch -> one PR.
- Use descriptive branch prefixes such as `feat/`, `fix/`, `chore/`, or the repository's established convention.
- Reuse an existing matching PR rather than opening a duplicate.
- Keep PRs reviewable and explain behavioral impact, not just filenames changed.
- Do not merge automatically unless the user has clearly authorized merging.
- When creating a PR before verification is complete, keep it as draft when the platform supports drafts.

Use `assets/issue-template.md` and `assets/pr-template.md` when the repository does not already provide better templates.

## Verification

Determine the project's real quality gates from its configuration instead of inventing generic commands.

Verify in layers as applicable:

1. Focused checks for the changed area.
2. Lint, formatting, type checks, tests, and build commands that the repo actually uses.
3. Integration or manual flow checks for behavior that unit tests cannot prove.
4. UI changes: inspect the rendered result or exercise the actual interaction when tools allow it.
5. Deployed apps: perform a production smoke test of the core changed flow when deployment is part of the task.

Do not equate "tests passed" with "the user-facing feature works" when those are different claims.

If local or production verification is impossible from the available environment, state exactly what was verified and what remains unverified.

## Definition of done

A change is done when the requested behavior is implemented and the strongest applicable verification has passed.

For deployed projects, do not call a change fully shipped merely because CI or deployment reported success; verify the relevant production flow when possible.

At handoff, report concisely:

- what changed,
- what was verified,
- any remaining risk or unverified step,
- the current Issue/branch/PR when one exists,
- the next action only when useful.

## Avoid process theater

Never create Issues, specs, branches, documents, or ceremonies only to satisfy this skill. Every artifact must make the work easier to understand, continue, review, or verify.
