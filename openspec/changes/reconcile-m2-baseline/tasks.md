# Tasks: Reconcile the M2 baseline

- [x] 1. [All requirements] Run `bd prime`, create Beads tasks mirroring this checklist, and record dependencies without duplicating requirement text.
- [x] 2. [R1–R7] Audit README and `doc/*.md` against current code, migrations, and tests; if a production defect is discovered, create a follow-up Bead rather than expanding this change.
- [x] 3. [R3–R6] Correct README's contradictory M2 completion/non-completion claims and document the exact commands, memory categories/statuses, and five-memory recall limit.
- [x] 4. [R1–R7] Update `doc/PROJECT_OVERVIEW.md`, `doc/ARCHITECTURE.md`, `doc/M0_FOUNDATION.md`, `doc/M1_TEXT_CHAT.md`, and `doc/M2_MEMORY.md` so paths and completed behavior match the baseline specification.
- [x] 5. [R3] Remove remaining completed-scope references to `/explain`; its explanation behavior remains part of `/help`.
- [x] 6. [R1–R7] Delete `doc/AI_Learning_Companion_Technical_Spec.md` after confirming every still-valid repository constraint is represented by OpenSpec or the concise documents.
- [x] 7. [R1–R7] Search for contradictory `docs/` paths, 20-memory limits, and claims that private/audit/candidate/`/memory` workflows are completed; correct or explicitly defer them.
- [x] 8. [R7] Run Ruff, strict mypy, and the complete ordinary pytest suite; do not run live Groq tests.
- [x] 9. [All requirements] Update the Beads task states, summarize changed documents and validation, and prepare a focused PR without unrelated code changes.
