## 1. Persistence and Contracts

- [x] 1.1 Add validated proactive timing and delivery-limit settings plus API/domain enums and schemas; verify schema tests cover valid and rejected values. (Requirements: Core determines invitation eligibility and priority; User can accept, snooze, or dismiss an invitation)
- [x] 1.2 Add the `proactive_invitations` SQLAlchemy model and Alembic revision after `20260810_0004`; verify upgrade creates all indexes/columns and downgrade removes only the new table. (Requirement: Invitation delivery is singular, bounded, and persistent)
- [x] 1.3 Implement the proactive repository for pending lookup, local-date delivery counts, creation, and atomic expected-status resolution; verify repository tests prevent duplicate resolution. (Requirements: Invitation delivery is singular, bounded, and persistent; User can accept, snooze, or dismiss an invitation)

## 2. Core Policy and API

- [x] 2.1 Implement `ProactiveService.check` with injectable clock, availability suppression, UI-presentability and idle thresholds, review priority, cooldown, dismissal, and daily-limit policy; verify fake-clock unit tests cover every suppression boundary. (Requirement: Core determines invitation eligibility and priority)
- [x] 2.2 Implement deterministic local conversation-starter rotation and persist the selected key/text; verify repeated checks and restarts return identical content without provider calls. (Requirements: Invitation delivery is singular, bounded, and persistent; Accepted conversation practice joins normal chat)
- [x] 2.3 Implement start, snooze, and dismiss-today decisions with timezone-aware boundaries and safe stale/duplicate handling; verify unit tests cover review state changing before acceptance and midnight rollover. (Requirement: User can accept, snooze, or dismiss an invitation)
- [x] 2.4 Wire proactive dependencies and add `POST /v1/proactive/check` plus `POST /v1/proactive/invitations/{id}/respond`; verify typed responses reuse `LearningService.first_due()` and map not-found/conflict errors without exposing internal failures. (Requirements: Core determines invitation eligibility and priority; User can accept, snooze, or dismiss an invitation)

## 3. Terminal Interaction

- [x] 3.1 Add low-frequency invitation polling and idle tracking to Textual, reporting `can_present=false` during help, hint, help-result, review, and in-flight request states; verify no poll interrupts existing modes. (Requirement: Terminal presents invitations without interrupting active work)
- [x] 3.2 Render one distinct invitation card with Start, Later, and Not today actions, reuse the existing review state on accepted review invitations, and remove the card only after a confirmed decision. (Requirements: Terminal presents invitations without interrupting active work; User can accept, snooze, or dismiss an invitation)
- [x] 3.3 Display an accepted deterministic conversation starter without writing it as transcript data, then route the user's next ordinary text through the existing conversation message flow. (Requirement: Accepted conversation practice joins normal chat)
- [x] 3.4 Keep conversation/input state usable across proactive check and decision failures and show only controlled system feedback; verify terminal tests cover retryable cards and offline Core behavior. (Requirement: Terminal presents invitations without interrupting active work)

## 4. Verification and Documentation

- [x] 4.1 Add unit and integration coverage proving polling and acceptance never call the LLM, pending invitations survive new sessions, daily limits persist, and proactive starters do not enter learning or memory tables. (Requirements: Core determines invitation eligibility and priority; Invitation delivery is singular, bounded, and persistent; Accepted conversation practice joins normal chat)
- [x] 4.2 Add `doc/M4_PROACTIVE.md` and update `README.md`, `doc/PROJECT_OVERVIEW.md`, `doc/ARCHITECTURE.md`, and `.env.example` with exact M4 scope, defaults, demo overrides, migration command, and explicit closed-app notification exclusions. (Requirements: all proactive-practice requirements)
- [x] 4.3 Run strict OpenSpec validation, Alembic upgrade/downgrade validation, Ruff, strict mypy, and the complete ordinary pytest suite; record exact passing results without running live Groq tests. (Requirements: all proactive-practice requirements)
