# Issue #28 — Codex Execution Contract

Source issue: https://github.com/Lilian0414/teacher/issues/28

## Goal

Restore a supported Groq default model and verify the complete existing LLM contract without changing Teacher's learning loop, memory policy, provider architecture, or database schema.

## Ownership

- ChatGPT owns planning, GitHub orchestration, review, CI verification, and merge decisions.
- Codex owns all production implementation for this issue.
- Do not rely on ChatGPT-authored production patches.
- Do not merge any implementation PR.

## Base and delivery

1. Start from the latest `main` that contains this planning contract.
2. Create a focused implementation branch named like `codex/issue-28-groq-contract` (or another clearly issue-linked branch).
3. Implement only Issue #28.
4. Push the implementation branch to GitHub.
5. Open a child PR targeting `main`, linked to Issue #28. If the environment cannot open the PR, pushing a GitHub-visible implementation branch is the minimum required delivery boundary; ChatGPT will create the PR.
6. Do not commit production implementation to this planning/spec branch.
7. Do not merge.

## Required implementation scope

- Verify and select a currently supported Groq model compatible with all existing Teacher LLM tasks:
  - normal chat;
  - Help structured output;
  - Hint structured output;
  - Say structured output;
  - explicit memory analysis;
  - conversation-end memory extraction.
- Update the repository default configuration, `.env.example`, and user-facing documentation that names the default model.
- Keep ordinary CI deterministic and offline.
- Preserve opt-in live tests and expand them as needed to exercise the domain-shaped Groq contracts.
- Make runtime status wording truthful: API-key presence alone must not claim that the configured provider/model is usable.
- Keep malformed/rejected structured output controlled and non-persistent.
- Never expose API keys or secrets.

## Non-goals

Do not add Japanese support, a new teacher personality, a new provider framework, a learning-state redesign, a memory-policy redesign, schema changes, or unrelated refactors.

## Required validation

Run the strongest applicable repository gates and report exact results:

- `ruff check .`
- `mypy .`
- `pytest`
- `git diff --check`
- the existing opt-in Groq live contract suite when valid credentials are available

If live credentials are unavailable in the Codex environment, do not fabricate a live-pass claim. Keep the suite opt-in, report that limitation explicitly, and provide deterministic offline coverage for request/response contract behavior.

## PR evidence

The implementation PR description must include:

- concise summary of what changed;
- the selected Groq model and why it satisfies the existing task shapes;
- exact validation commands and results;
- whether live Groq contract tests actually ran with credentials;
- any remaining risk or manual verification needed;
- `Closes #28`.

## Review boundary

Completion means a GitHub-visible implementation diff exists for review. A Codex task summary alone is not delivery. ChatGPT will independently inspect the diff, tests, CI, and issue acceptance criteria before merge.