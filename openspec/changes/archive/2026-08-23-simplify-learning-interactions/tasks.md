# Tasks: Simplify learning interactions and remove command-heavy UX

- [x] 1. [terminal-ui R1] Add `LearningRepository.due_count` and `LearningService.due_count`, add
      `due_review_count` to `StateResponse`, and wire it into the `/v1/state` route.
- [x] 2. [terminal-ui R1] Update `/v1/state`-covering integration tests to override
      `get_learning_service` and assert `due_review_count`; add a dedicated test that the count
      reflects a freshly created learning item.
- [x] 3. [terminal-ui R2, R3] Add an `InteractionMode` state machine to `terminal_ui/app.py` with
      Help me say it / Give me a hint / Review entry points (buttons + Ctrl+H / Ctrl+G / Ctrl+R),
      dispatching through the existing `/v1/commands/execute` path.
- [x] 4. [terminal-ui R3] Implement the Help me say it → Use this / Hint only / Try myself flow,
      reusing the existing `/say` and `/hint` command execution paths for the follow-up actions.
- [x] 5. [terminal-ui R4] Replace debug-style `[help]` / `[help alt]` / `[help zh]` /
      `[help correction]` / `[say] inserted` / `[review N]` rendering with structured, readable
      output; lightly clean up memory command rendering for consistency.
- [x] 6. [terminal-ui R1] Surface the due-review count as a passive status-bar indicator, updated on
      the existing 5-second poll, without any proactive message-log notification.
- [x] 7. [terminal-ui R2] Replace the command-list input placeholder with "Say something..." and
      restore it automatically when returning to normal mode.
- [x] 8. [All requirements] Rewrite `tests/unit/test_terminal_ui.py` for the new structured output
      and add coverage for: help intent reuses `/help`; hint intent reuses `/hint`; Use this reuses
      `/say` and does not create a learning item; Try myself returns to normal input without
      sending; due-review indicator reflects zero/non-zero counts; slash commands still dispatch
      through the unchanged `/v1/commands/execute` path.
- [x] 9. [All requirements] Run Ruff, strict mypy, the complete pytest suite, and OpenSpec
      validation; confirm no regression in `learning-loop` or `companion-baseline` behavior.
- [x] 10. [All requirements] Prepare a focused PR summarizing implementation, key files touched,
       test results, and known limitations; do not merge automatically.
