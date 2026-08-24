# AI Learning Companion

Mac-only AI English learning companion implemented through M4 in-app proactive practice.

The canonical M0–M4 capability matrix is in [`doc/PROJECT_OVERVIEW.md`](doc/PROJECT_OVERVIEW.md).

## Implemented

- Python 3.12 project structure under `src/companion`.
- FastAPI Core with `GET /health`, `GET /v1/state` and a limited M0 command endpoint.
- SQLite persistence with SQLAlchemy 2.x and Alembic.
- Availability states: `available`, `busy`, `dnd`.
- Availability overrides with expiration and DND priority rules.
- Deterministic parser for slash command names and arguments.
- English text conversations with persisted user and assistant messages.
- `/help <內容>` teaches a natural expression for Chinese or mixed input, or explains English
  in Chinese and only supplies a correction when needed; it does not send a message.
- `/hint <內容>` returns one to three words, phrases, or incomplete sentence patterns without
  sending a message.
- `/say <中文>` translates one utterance, stores it as the current conversation's user message,
  and continues with the normal assistant reply.
- Long-term memories stored in SQLite with categories `people`, `personal`, `school_work`,
  `relationships`, `health_fitness`, and `other`.
- Memory statuses are limited to `active` and soft-deleted `deleted`.
- Conversation-end extraction considers only persisted user messages and applies deterministic
  source, trivial-content, and exact-duplicate checks before storage.
- Relevant-memory recall adds at most five matching memories to normal chat context. Optional
  OpenAI-compatible embeddings enable hybrid semantic recall in the production runtime.
- Memory management commands: `/remember`, `/memories`, and confirmed `/forget`.
- `/help` and `/hint` create deduplicated learning items; `/say` never does.
- `/review` starts a resumable, one-question-at-a-time terminal review session.
- Review grading is local exact matching after case, whitespace and terminal-punctuation
  normalization; it never calls Groq.
- Correct review intervals are 1, 3, 7, 14 and then 30 days; an incorrect answer resets the
  item to stage zero and schedules it one day later.
- Up to three due learning goals can join, but remain separately labelled from, relevant life
  memory in normal conversation context.
- LLM provider interface with `FakeLLMProvider` for tests and `GroqLLMProvider` for live use.
- Textual UI showing messages, Core status, availability, reviews, and in-app proactive practice
  invitations while the UI is running (see `doc/M4_PROACTIVE.md`).
- pytest, pytest-asyncio, Ruff and mypy configuration.

## Memory Commands

```text
/remember <內容>              Save one explicit memory immediately
/memories [關鍵字]           List or search active memories
/forget <memory_id>          Preview a memory and request deletion confirmation
/forget <memory_id> confirm  Soft-delete the confirmed memory
```

Only user messages are sent to memory extraction. Greetings, assistant messages, candidates
with invalid source IDs, and exact duplicates are rejected by deterministic Core policy.
Deleted memories remain in SQLite with `status=deleted` but are excluded from recall and normal
listing. Chat recall always retains name/text matching and sends at most five relevant entries to
the configured LLM; it never sends the complete memory database. When embeddings are enabled,
new and updated memories are embedded and query recall uses compatible vectors. Older or
incompatible rows are lazily re-embedded, bounded by `EMBEDDING_BACKFILL_LIMIT` per query.
Provider errors fall back to lexical/person matching.

## Learning Review

```text
/review       Show the first due prompt and enter review mode
<your answer> Grade the active prompt, show feedback, then advance
/review quit  Leave review mode without changing the unanswered item
```

While reviewing, other slash commands still work and do not discard the active question. A
restart needs no persisted cursor: answered items retain their schedule, while an unanswered item
remains due. Learning prompts, accepted answers and attempt history live only in the learning
tables and are never inserted into long-term life memory.

## Current boundaries

M4 proactive practice is limited to invitations inside the running Textual UI. Private
conversations, memory sensitivity levels, candidate approval, audit history, conflict states,
memory editing, proactive-use permissions, closed-app/background notifications, voice, hardware,
webcam, and file tools remain future work. LangChain, Mem0, and Letta are
intentionally outside the current architecture.

## Setup and run (Apple Silicon)

Python 3.12 and a normal virtual environment are sufficient; no Intel Homebrew paths are
required. From a fresh clone:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
alembic upgrade head
companion
```

`companion` starts Core and the terminal UI together. Two-process development remains available:

```bash
companion-core
# in another terminal
companion-ui
```

Core and UI share `COMPANION_HOST` and `COMPANION_PORT`. The default SQLite database is
`~/Library/Application Support/ai-learning-companion/companion.sqlite3`, independent of the
current directory. Override it with an absolute URL such as
`COMPANION_DATABASE_URL=sqlite:////Users/me/data/companion.sqlite3`.

## Groq Settings

```env
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b
GROQ_BASE_URL=https://api.groq.com/openai/v1
LLM_TIMEOUT_SECONDS=30
MEMORY_CONTEXT_LIMIT=5
LEARNING_CONTEXT_LIMIT=3
EMBEDDINGS_ENABLED=false
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_API_KEY=
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
EMBEDDING_TIMEOUT_SECONDS=10
EMBEDDING_BACKFILL_LIMIT=10
```

Keep real `GROQ_API_KEY` values in `.env` or the shell environment only. `/v1/state` reports a
present key as `key_present_unverified` until an actual request proves the configured model is
usable. Provider/model failures include the model and Groq's safe error detail, never the key.
Embeddings are disabled by default. The embedding endpoint is OpenAI-compatible and may be a
local server such as Ollama; model identity and exact dimensions are stored with every vector so
incompatible vectors are never compared silently.

## Reproducible dependencies and validation

[`requirements.lock`](requirements.lock) pins application and development dependencies for Python 3.12. Install exactly
that environment and run the same checks as CI with:

```bash
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
ruff check .
mypy .
pytest
```

Ordinary tests keep embeddings disabled and live Groq coverage opt-in, so these commands require no
API credentials. Maintainers refresh the lock deliberately after reviewing dependency updates:

```bash
python -m pip install --upgrade -e ".[dev]"
python -m pip freeze --exclude-editable | sed '/^pip==/d' > requirements.lock
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
```

Commit `pyproject.toml` and `requirements.lock` together after the complete validation suite passes.
