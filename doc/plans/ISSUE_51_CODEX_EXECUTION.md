# Issue #51 Codex execution contract

Source: GitHub Issue #51 — Restore clean application startup from an installed package.

Base: `main` at `4f42256b21ba401f68bd4d4e45dc20218e3824d9`.

Priority: P0. This blocks every real user flow because neither official local entry point can start Core from a clean installation.

## Goal

Make application startup independent of import order.

A fresh installed interpreter must be able to import the FastAPI app, `companion-core` must reach `GET /health`, and `companion` must be able to launch the same Core child. The fix must preserve existing provider/service behavior and public CLI contracts.

## Verified failure on current main

The acceptance audit used a brand-new virtual environment and the documented package installation path.

These official paths fail immediately:

```bash
companion-core
python -c "from companion.main import app"
```

Observed import chain:

```text
companion.main
  -> companion.api.routes
  -> companion.api.dependencies
  -> companion.learning.service
  -> companion.providers.schemas
  -> companion.providers.__init__
  -> companion.providers.fake
  -> companion.memory.schemas
  -> companion.memory.__init__
  -> companion.memory.service
  -> companion.conversation.repository
  -> companion.conversation.__init__
  -> companion.conversation.service
  -> partially initialized companion.learning.service
```

The same process happens in the Core child launched by `companion`.

Pre-importing `companion.api.dependencies` happened to change the import order enough to let the audit continue. That is only evidence of an order-dependent cycle; it is not an allowed workaround.

## Root design boundary

Importing `companion.providers.schemas` first executes `companion.providers.__init__`. The initializer currently eagerly imports `FakeLLMProvider`; the fake provider imports memory schemas, and the memory/conversation package re-exports eagerly pull service modules back into the partially initialized learning module.

Fix the package/module dependency direction rather than reordering imports until one entry point happens to work.

Preferred minimal approach:

1. Make package initializers lightweight and cycle-safe.
2. Import concrete provider implementations from their defining modules at the composition root (`companion.api.dependencies`) rather than forcing every `companion.providers.*` import to load fake, Groq, embeddings, memory, conversation, and learning services.
3. If top-level re-export compatibility is required, implement it without eager service imports (for example a narrowly typed lazy export), and cover that compatibility explicitly.
4. Use direct module imports and `TYPE_CHECKING`-only imports where a dependency exists only for type annotations.
5. Review `conversation/__init__.py` and `memory/__init__.py` for the same eager-re-export pattern. Change only what is necessary to make supported import paths deterministic.

Do not solve this with a preparatory import, a catch-all exception, a startup sleep, or by moving the crash until the first request.

## Required runtime behavior

1. `from companion.main import app` succeeds in a new Python process with an empty `PYTHONPATH` and a working directory outside the repository.
2. `companion-core` starts without Groq/Ollama access when configured with the fake/offline profile, reaches `GET /health`, and terminates cleanly.
3. `companion` launches the Core child through the same fixed path rather than a separate test-only path.
4. Existing imports used by application code and tests remain valid, or are replaced consistently with documented direct-module imports.
5. Provider construction stays in the API dependency/composition layer. Importing schemas/protocols must not instantiate providers or import unrelated domain services.
6. No database schema change is expected.

## Required regression coverage

### Installed import smoke

Extend packaging coverage so a subprocess launched outside the repository imports at least:

```python
from companion.main import app
from companion.api.dependencies import get_llm_provider
```

Requirements:

- clear `PYTHONPATH`;
- use the installed package;
- assert process exit code and capture stderr so the old circular traceback is visible on failure;
- do not make network calls.

The existing `tests/packaging/test_installed_ui.py` only imports `terminal_ui.app`; keeping that test green is necessary but not sufficient.

### Core readiness smoke

Start the installed `companion-core` command as a subprocess with:

- `LLM_PROVIDER=fake`;
- embeddings disabled;
- isolated temporary SQLite configuration;
- a test-owned local port.

Poll `GET /health` with a bounded timeout. Assert the expected `status=ok` response, then terminate the child and assert clean bounded shutdown. Always clean up the process in a `finally` block so a failing test cannot leave a server behind.

Do not rely only on a fixed sleep.

### Import-order regression matrix

Add a small parametrized subprocess test for representative supported first imports, including:

- `companion.main`;
- `companion.api.dependencies`;
- `companion.providers.schemas`;
- `companion.providers.fake`;
- `companion.learning.service`;
- `companion.memory.service`;
- `companion.conversation.service`.

Each case must run in a fresh interpreter. One process importing all modules in a favorable order does not prove the bug is fixed.

### Local launcher coverage

Add the strongest deterministic coverage practical for `companion.cli.local` without driving an indefinite Textual session. At minimum prove that it uses the fixed `core` target and performs bounded child cleanup if UI startup exits/fails. The real installed Core readiness smoke remains the primary launch proof.

## Likely touch points

- `src/companion/providers/__init__.py`
- `src/companion/api/dependencies.py`
- possibly `src/companion/conversation/__init__.py`
- possibly `src/companion/memory/__init__.py`
- `tests/packaging/test_installed_ui.py` or a new focused packaging/startup test
- focused CLI tests only if needed

Avoid changes to learning, memory, or proactive domain behavior.

## Non-goals

- No provider redesign or new dependency-injection framework.
- No changes to learning-item identity, assistant retry UX, proactive recovery, memory retrieval, review scheduling, or timezone display; those are tracked separately.
- No automatic Groq/Ollama installation or live-provider requirement.
- No general CLI rewrite.
- No migration.

## Required verification

Run and report:

```bash
ruff check .
mypy src tests
pytest
TZ=Asia/Taipei pytest tests/packaging <focused startup/CLI tests>
git diff --check
```

Also run a fresh-environment acceptance outside the worktree using the documented install path, then show:

1. installed-package location;
2. successful `from companion.main import app`;
3. `companion-core` health response;
4. bounded shutdown result.

Run the current migration chain to head on a fresh temporary SQLite database. Report any pre-existing unrelated timezone failure separately; do not broaden this P0 fix into the final UAT tracked by #55.

## Delivery guard

This is one focused Codex implementation run for Issue #51.

- Start implementation from the latest `main`, confirming it still contains the audited failure before editing.
- If equivalent work already merged, stop and report the duplicate instead of reimplementing it.
- Keep production changes and regression tests limited to #51.
- Do not merge.
- Publish a GitHub-visible implementation PR linked to #51. The planning PR is the execution anchor, not the implementation delivery.
- If PR publication is blocked but the environment exposes Create PR, leave the completed committed branch ready for that handoff and report the exact branch/commit.
- Preserve completed work if publication is blocked.
- ChatGPT/planner owns review, CI verification, focused follow-up, and merge decision.
