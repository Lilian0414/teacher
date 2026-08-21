# AI Learning Companion

Mac-only M3 implementation for the AI English learning companion.

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
- Relevant-memory recall adds at most five matching memories to normal chat context.
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
listing. Chat recall searches by names and text overlap and sends at most five relevant entries
to the configured LLM; it never sends the complete memory database.

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

## Not Implemented In M3

Private conversations, memory sensitivity levels, candidate approval, audit history, conflict
states, memory editing, proactive-use permissions, proactive invitations and background reminders,
voice, hardware, webcam, and file tools are future work. LangChain, Mem0, and Letta are
intentionally outside the current architecture.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Groq Settings

```env
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_BASE_URL=https://api.groq.com/openai/v1
LLM_TIMEOUT_SECONDS=30
MEMORY_CONTEXT_LIMIT=5
LEARNING_CONTEXT_LIMIT=3
```

Keep real `GROQ_API_KEY` values in `.env` or the shell environment only.
`.env.example` intentionally leaves the key blank.

## Run Core

```bash
DYLD_LIBRARY_PATH=/usr/local/opt/expat/lib .venv/bin/uvicorn companion.main:app --reload
```

## Migration

```bash
DYLD_LIBRARY_PATH=/usr/local/opt/expat/lib .venv/bin/alembic upgrade head
```

## Run UI

```bash
DYLD_LIBRARY_PATH=/usr/local/opt/expat/lib .venv/bin/python -m terminal_ui.app
```

## Validate

```bash
DYLD_LIBRARY_PATH=/usr/local/opt/expat/lib .venv/bin/ruff check .
DYLD_LIBRARY_PATH=/usr/local/opt/expat/lib .venv/bin/mypy .
DYLD_LIBRARY_PATH=/usr/local/opt/expat/lib .venv/bin/pytest
```

Live Groq smoke test:

```bash
RUN_LIVE_API_TESTS=1 DYLD_LIBRARY_PATH=/usr/local/opt/expat/lib \
  .venv/bin/pytest tests/live/test_groq_live.py
```

On this Mac, Homebrew Python 3.12 needs the `DYLD_LIBRARY_PATH` above so `pyexpat`
loads Homebrew `expat` instead of the older system library.
