# Decision guide

Use the lightest workflow that preserves enough context and confidence for the change.

## Quick change examples

Usually no Issue is needed:

- text/copy correction
- minor visual spacing or color adjustment
- narrow configuration fix
- obvious one-line or localized bug
- tiny developer-experience cleanup with no behavior change

Escalate to a scoped change when the edit touches public behavior, data, APIs, authentication, migrations, billing, security, or multiple coupled areas.

## Scoped change examples

Usually deserves durable planning and a PR:

- new user-facing capability
- changing when or how an existing feature triggers
- persistent state or database changes
- API contract changes
- a bug whose root cause crosses components
- meaningful dependency upgrades
- work expected to continue across sessions or agents

If OpenSpec is already present, prefer its existing change lifecycle. Do not duplicate the same requirements in both an OpenSpec proposal and a GitHub Issue unless the repository intentionally uses both for different purposes.

## Large or unclear examples

Explore first:

- "redesign the learning loop"
- "make this app feel less AI-generated"
- "replace the translation architecture"
- "make the assistant proactively engage users" when triggers and boundaries are still undefined
- requests containing several independent outcomes

The exploration should end with a small number of clear decisions or separable scoped changes, not an oversized implementation plan.

## Choosing between OpenSpec and GitHub Issues

Use the repository's existing system.

If OpenSpec exists and is actively used:

- idea/uncertainty -> OpenSpec explore
- stable behavior change -> OpenSpec proposal/change artifacts
- implementation -> OpenSpec apply workflow
- archive/sync -> existing OpenSpec archive/sync workflow

Use GitHub Issues for bug reports, backlog, coordination, or repositories that do not have a stronger spec system.

Do not make the user manage duplicate status in several places.

## When the user wants to move fast

Speed does not require skipping all discipline.

For a small urgent fix:

1. reproduce or identify the problem,
2. make the smallest fix,
3. run focused verification,
4. preserve a clean commit/PR trail when working remotely.

For a risky urgent fix, shorten planning but keep explicit rollback/verification thinking.

## Existing work takes priority

Before starting new work, search for:

- an active branch with the same goal,
- an open PR,
- an open Issue,
- an active OpenSpec change,
- partially completed tasks or TODOs tied to the same change.

Continue the existing artifact when appropriate. Avoid parallel duplicate implementation.

## UI and UX work

Tests are not sufficient evidence for appearance or interaction quality.

When tools permit:

- render the affected screen,
- exercise the changed interaction,
- check responsive/mobile behavior when relevant,
- check loading, empty, error, and disabled states when they are part of the flow.

Treat visual verification as part of implementation, not an optional polish step.

## Deployment

If the project is deployable and the user asks to ship:

1. verify the merge target and CI status,
2. merge only with authorization,
3. confirm deployment completes,
4. exercise the changed production path,
5. report production-specific problems separately from source-code success.

If the project has no deployment or the change is docs/local-only, skip production verification explicitly rather than pretending it applies.

## New findings

Classify newly found work:

- required to satisfy current acceptance -> include it,
- required to unblock current work -> include the minimum necessary and explain,
- useful but independent -> new Issue/backlog item,
- speculative cleanup -> leave it alone unless requested.

This keeps PRs coherent and makes future agents able to understand why each change exists.
