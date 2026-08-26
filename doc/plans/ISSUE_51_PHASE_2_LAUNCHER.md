# Issue #51 Phase 2 — local launcher readiness and cleanup

Source: GitHub Issue #51.

Base: current `main` after Phase 1 merge `768f0a0cbec3899aef8f69df77a282e8c876fccd`.

## Goal

Finish the deterministic launcher portion of Issue #51 without broadening into final real-Mac/provider UAT.

Phase 1 already proved the installed `companion-core` path can import cleanly and serve `/health` in an offline fake-provider profile. The remaining launcher gap is `companion.cli.local()`: it currently starts a Core child, sleeps a fixed 0.5 seconds, launches the Textual UI, then terminates the child in `finally`.

That fixed delay is not a readiness contract. On a slower machine the UI can start before Core is usable; if the Core child exits during startup, the UI can still be launched.

## Required behavior

1. `companion` must start the same supported Core target used by `companion-core`.
2. After starting the child, the launcher must wait for Core readiness with a bounded poll of `GET /health` instead of a fixed startup sleep.
3. The readiness check must use the configured host/port and must not require Groq/Ollama when the fake/offline profile is selected.
4. If the Core child exits before readiness, fail before launching the UI and surface a controlled launcher error.
5. If Core does not become ready before a bounded timeout, fail before launching the UI.
6. Whether UI exits normally or raises during startup/runtime, the Core child must be cleaned up deterministically and `join()` must be bounded. A stuck child must not be left behind.
7. Keep normal `companion-core` and `companion-ui` entry points unchanged.

## Preferred implementation shape

Keep this small and testable. A narrow private readiness helper in `companion.cli` is acceptable. Prefer polling `/health` with an existing dependency or stdlib HTTP client; do not add a new dependency.

Do not introduce a background supervisor framework, IPC redesign, process manager, daemonization, retry subsystem, or UI rewrite.

Avoid a fixed `sleep()` as the readiness mechanism. Short sleeps between bounded poll attempts are fine.

## Required deterministic tests

Add focused unit/packaging coverage that proves:

- `local()` starts the Core child and waits for health before calling the UI runner;
- UI is not called if the child exits before readiness;
- UI is not called after readiness timeout;
- UI exception still cleans and joins the Core child;
- normal UI return cleans and joins the Core child;
- cleanup has a bounded fallback for a child that does not exit promptly;
- the launcher uses configured host/port rather than hard-coded production values.

Use fakes/mocks for child-process lifecycle tests so CI does not need to drive an indefinite Textual session. Reuse the Phase 1 installed `companion-core` smoke as the real Core startup proof; do not duplicate a second heavy server integration unless it reveals a real gap.

## Non-goals

- No changes to learning, review, memory, proactive behavior, `/say`, retry semantics, or scheduling.
- No provider redesign.
- No database migration.
- No live Groq/Ollama acceptance.
- No macOS keyboard/Textual long-session automation.
- No timezone work.
- Do not absorb Issues #52–#55.

Real installed macOS/Textual and live-provider acceptance belongs to Issue #55.

## Verification

Run and report:

```bash
ruff check .
mypy .
pytest
TZ=Asia/Taipei pytest tests/packaging tests/unit/test_cli.py -q  # adapt focused path if test file differs
git diff --check
```

Keep the existing Phase 1 installed Core smoke green.

## Delivery model

Use the delivery pattern that succeeded for Issue #51 Phase 1 / Issue #29:

- work from this planning branch as the task base;
- implementation may be committed directly on the planning head or on a child `codex/...` branch;
- complete code and tests first;
- if Push/Create PR is unavailable in Codex, publication failure is not task failure;
- preserve the completed commit/branch and report exact commit, tests, and publication blocker;
- do not discard or redo completed work solely because PR publication is unavailable;
- do not merge.

ChatGPT owns final diff review, current-head CI verification, and merge decision.
