## 1. Persistence foundation

- [x] 1.1 Add the learning-item and learning-attempt SQLAlchemy models plus an additive Alembic migration with uniqueness, foreign-key, due-time, and history indexes. (Requirements: Learning items are deduplicated and persisted; Review results advance a simple deterministic schedule)
- [x] 1.2 Add typed learning schemas, normalization helpers, and repository operations for atomic create-or-update, due-item selection, stale-answer protection, attempt creation, and stage/date updates. (Requirements: Learning items are deduplicated and persisted; Answer evaluation is deterministic and local)
- [x] 1.3 Add repository and migration tests proving deduplication, stable due ordering, persistence across sessions, attempt history, and downgrade/upgrade behavior. (Requirements: Learning items are deduplicated and persisted; Review results advance a simple deterministic schedule)

## 2. Learning capture and review policy

- [x] 2.1 Implement a learning service that maps successful `/help` and `/hint` outputs into expression or phrase items, merges accepted answers, excludes `/say`, and uses the injected clock. (Requirement: Successful language assistance creates a learning item)
- [x] 2.2 Implement deterministic local grading and the capped 1/3/7/14/30-day stage policy, including atomic attempt recording and stale/not-due errors. (Requirements: Answer evaluation is deterministic and local; Review results advance a simple deterministic schedule)
- [x] 2.3 Add unit tests for answer extraction, no-answer and `/say` exclusions, normalization, correct/incorrect transitions, interval capping, and no LLM call during grading. (Requirements: Successful language assistance creates a learning item; Answer evaluation is deterministic and local; Review results advance a simple deterministic schedule)

## 3. Core API and command integration

- [x] 3.1 Extend command parsing and structured command schemas so `/review` starts review and `/review quit` is recognized without changing other command behavior. (Requirement: Review is an interactive one-question-at-a-time session)
- [x] 3.2 Wire the learning service into successful `/help` and `/hint` command execution and expose the stored learning item without writing conversation messages or life memories. (Requirements: Successful language assistance creates a learning item; Due learning goals influence conversation context)
- [x] 3.3 Add Core endpoints/schemas to fetch the first due question and submit one item-addressed answer, returning feedback, accepted answers, scheduling state, and the next due question. (Requirements: Review is an interactive one-question-at-a-time session; Answer evaluation is deterministic and local; Review results advance a simple deterministic schedule)
- [x] 3.4 Add API integration tests for no-due, one-at-a-time ordering, correct and incorrect answers, stale duplicate submissions, command availability, and persisted restart/resume behavior. (Requirements: Review is an interactive one-question-at-a-time session; Learning items are deduplicated and persisted)

## 4. Conversation context

- [x] 4.1 Add a bounded learning-context builder that selects due goals deterministically and labels prompts separately from accepted answers and life-memory context. (Requirement: Due learning goals influence conversation context)
- [x] 4.2 Compose due learning context with existing relevant active-memory context in normal conversation replies while preserving recent-message limits and omitting empty sections. (Requirement: Due learning goals influence conversation context)
- [x] 4.3 Add unit and integration tests showing combined context, independent limits, absence when nothing is due, and strict separation from memory storage/search. (Requirement: Due learning goals influence conversation context)

## 5. Terminal interaction

- [x] 5.1 Add transient terminal review state so `/review` displays one question, the next non-command input submits its answer, feedback advances to the next item, and completion leaves review mode. (Requirement: Review is an interactive one-question-at-a-time session)
- [x] 5.2 Implement `/review quit`, preserve the active unanswered item across other slash commands, and ensure interrupted sessions resume through due-item state rather than a persisted cursor. (Requirement: Review is an interactive one-question-at-a-time session)
- [x] 5.3 Add terminal tests for question rendering, answer routing, feedback, next-item progression, exit, command interleaving, network failure, and final completion. (Requirement: Review is an interactive one-question-at-a-time session)

## 6. Documentation and validation

- [x] 6.1 Update README and M3 documentation with learning capture rules, interactive `/review` usage, deterministic grading/schedule, data boundaries, and exclusions. (Requirements: all learning-loop requirements)
- [x] 6.2 Run Ruff, strict mypy, complete non-live pytest, Alembic migration checks, and strict OpenSpec validation without enabling Groq live tests. (Requirements: all learning-loop requirements)
