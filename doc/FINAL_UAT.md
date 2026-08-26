# Issue #55 final UAT guide

This guide is the **manual target-Mac acceptance run**. Automated tests and the preflight
snapshot do not prove that macOS, Groq, Ollama, or the real Textual interaction passed. Leave every
PASS/FAIL field blank until the action has been performed on the target Mac. Never paste keys or
tokens into evidence.

## Clean target profile

From a fresh clone at the commit being accepted:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
cp -f .env.example .env
```

Edit `.env` locally. Confirm `COMPANION_TIMEZONE=Asia/Taipei`, `LLM_PROVIDER=groq`, the intended
`GROQ_MODEL`, `EMBEDDINGS_ENABLED=true`, `EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1`,
`EMBEDDING_MODEL=nomic-embed-text`, and `EMBEDDING_DIMENSIONS=768`. Put the real Groq key only in
`.env`; do not copy it into logs or this checklist.

Use a new UAT database and migrate it from empty:

```bash
export COMPANION_DATABASE_URL="sqlite:////Users/$USER/Library/Application Support/ai-learning-companion/final-uat.sqlite3"
rm -f "/Users/$USER/Library/Application Support/ai-learning-companion/final-uat.sqlite3"
alembic upgrade head
ollama serve                         # separate terminal
ollama pull nomic-embed-text         # once, before the run
ollama list
companion                            # start Core and UI
```

In a separate activated shell with the same `.env` and database setting, capture the read-only,
allow-listed snapshot. It reports credential presence only as `present (redacted)` and performs
only Core GET requests and read-only database inspection:

```bash
companion-uat-evidence | tee final-uat-preflight.json
```

Record the commit, configured timezone/provider/models/embedding endpoint/dimensions, database
path, matching Alembic head/current revision, `/health`, and `/v1/state`. Also record the relevant
`ollama list` row without unrelated local information. A configured status is not proof that a
live request succeeds; the matrix below must exercise both providers.

## Read-only database evidence

After each scenario, exit or pause input, then use SQLite read-only mode. Replace the example IDs
with IDs visible in prior evidence; do not include private message or memory content unless needed
to demonstrate the acceptance point.

```bash
DB="/Users/$USER/Library/Application Support/ai-learning-companion/final-uat.sqlite3"
sqlite3 -readonly "$DB" <<'SQL'
.headers on
.mode box
SELECT 'conversations' AS entity, count(*) AS total FROM conversations
UNION ALL SELECT 'messages', count(*) FROM messages
UNION ALL SELECT 'learning_items', count(*) FROM learning_items
UNION ALL SELECT 'learning_occurrences', count(*) FROM learning_occurrences
UNION ALL SELECT 'learning_attempts', count(*) FROM learning_attempts
UNION ALL SELECT 'memories', count(*) FROM memories
UNION ALL SELECT 'proactive_invitations', count(*) FROM proactive_invitations;
SELECT id, role, source, created_at FROM messages ORDER BY created_at;
SELECT id, kind, stage, next_review_at FROM learning_items ORDER BY created_at;
SELECT id, learning_item_id, source_conversation_id, source_user_message_id,
       source_assistant_message_id, acceptance_reason FROM learning_occurrences;
SELECT id, learning_item_id, correct, stage_before, stage_after, attempted_at
FROM learning_attempts ORDER BY attempted_at;
SELECT id, category, status, embedding_model, embedding_dimensions,
       source_conversation_id FROM memories ORDER BY created_at;
SELECT id, kind, status, conversation_id, user_message_id, assistant_message_id,
       learning_occurrence_id, learning_item_id, outcome, completed_at
FROM proactive_invitations ORDER BY created_at;
SQL
```

Save evidence with timestamps and section numbers. Redact secrets and unnecessary personal text.

## Acceptance matrix

### 1. Ordinary chat and learning capture

- **User action:** Start a conversation, send an ordinary English message that naturally produces
  a clear correction/learning signal, and wait for the real Groq reply.
- **Expected UI:** User text and one assistant reply appear; no accepted answer is exposed as a
  review prompt; the UI remains responsive.
- **API evidence:** Record `/v1/state` status/provider/model before the action and the conversation
  message result/status and returned user/assistant IDs (redacted content is acceptable).
- **DB evidence:** Record conversation/message IDs and roles, then the learning item and occurrence
  IDs, kind, acceptance reason, source message IDs, stage, and due instant.
- **PASS/FAIL:** ____
- **Notes/evidence:** ____

### 2. Help to hint to review

- **User action:** Use Help me say it for a chosen sentence, select Hint only, then start Review and
  attempt the resulting question.
- **Expected UI:** Help gives a suggestion and actions; hint is partial; review initially shows only
  the prompt/kind, reveals accepted answers only after the attempt, and displays the next due time
  explicitly in `Asia/Taipei`.
- **API evidence:** Record command names/statuses and review question/item ID; record the submission
  result, correctness, stage, next due instant, and whether another question was returned.
- **DB evidence:** Record learning item/occurrence/attempt IDs, source IDs, submitted outcome,
  stage-before/stage-after, and next-review timestamp.
- **PASS/FAIL:** ____
- **Notes/evidence:** ____

### 3. Review correctness and scheduling

- **User action:** Attempt controlled correct and incorrect answers (including normalization cases),
  quitting before one attempt and resuming it.
- **Expected UI:** Verdicts match the answers; answers are hidden before submission; correct stages
  use 1/3/7/14/30-day intervals, incorrect resets to stage zero plus one day, and quit/resume leaves
  the unanswered item unchanged. Displayed due times use `Asia/Taipei` regardless of shell `TZ`.
- **API evidence:** Record each question ID, submission status, correctness, stage, canonical due
  instant, quit result, and resumed question ID.
- **DB evidence:** Record item stage/due values and attempt stage-before/stage-after/timestamps before
  and after each action; confirm no attempt for the quit-only question.
- **PASS/FAIL:** ____
- **Notes/evidence:** ____

### 4. Proactive end-to-end and interruption recovery

- **User action:** Meet an invitation eligibility condition, accept it, begin practice, interrupt or
  restart once, resume, submit an answer, and also exercise Later and Not today.
- **Expected UI:** Exactly one pending invitation is shown; accepted practice resumes without
  duplicating messages; the completed outcome is visible; snooze/dismiss suppress as documented.
- **API evidence:** Record check/respond/finalize statuses, invitation ID/status/outcome,
  conversation and message IDs, plus the recovered pending state after restart.
- **DB evidence:** Record invitation transition fields and linked conversation/message/learning
  occurrence/item IDs; confirm one finalized outcome and no duplicate practice messages.
- **PASS/FAIL:** ____
- **Notes/evidence:** ____

### 5. Cross-conversation semantic memory recall and false-positive check

- **User action:** In conversation A state a memorable fact, end it to extract memory, then in
  conversation B ask a genuinely semantically related question with **zero direct lexical overlap**.
  Also ask an unrelated question as the false-positive control.
- **Expected UI:** The real Groq reply to the semantic query uses the fact appropriately; the
  unrelated reply does not inject it. Separately disabling Ollama may demonstrate lexical fallback,
  but does not replace this real embedding run.
- **API evidence:** Record successful conversation/end/message statuses and IDs, real configured
  Groq model, and that Ollama `nomic-embed-text` was available for both extraction and query.
- **DB evidence:** Record memory ID/status/source conversation, embedding model/dimensions, and the
  two new conversation/message IDs; record the two queries to establish overlap/control without
  exposing unrelated private data.
- **PASS/FAIL:** ____
- **Notes/evidence:** ____

### 6. `/say` and assistant retry across say, chat, and practice

- **User action:** Run `/say` and confirm translation plus reply; for ordinary chat, `/say`, and
  proactive practice, induce one assistant-provider failure and invoke Retry after recovery.
- **Expected UI:** Each user message is stored once; failure is clear and retryable; retry adds one
  assistant response without duplicating the user turn; practice can then finalize once.
- **API evidence:** Record initial failure and retry status for each flow, conversation/user-message
  IDs, returned assistant-message ID, conflict status if retried again, and practice finalize result.
- **DB evidence:** For each flow record exactly one user and one successful assistant row linked to
  the conversation; record practice invitation links/outcome and any learning occurrence.
- **PASS/FAIL:** ____
- **Notes/evidence:** ____

### 7. UI, Core, and database consistency

- **User action:** Compare the final UI transcript/status with `/health`, `/v1/state`, and the
  read-only database snapshot; restart `companion` and check the recoverable state again.
- **Expected UI:** Availability, due count, review/proactive state, conversation history behavior,
  and explicit `Asia/Taipei` review time agree with Core and persisted state after restart.
- **API evidence:** Record final and post-restart `/health` and `/v1/state`, including timezone,
  provider/model status, availability, due count, and relevant resource IDs/results.
- **DB evidence:** Attach the final count/ID/state queries above, Alembic current/head, and targeted
  rows supporting every section; explain any intentional non-persisted UI-only state.
- **PASS/FAIL:** ____
- **Notes/evidence:** ____

## Sign-off boundary

Record target Mac model/macOS version, local date/time, commit SHA, operator, and evidence location.
Issue #55 passes only when all seven sections have real target-run evidence and PASS. CI or Codex
must not pre-fill these fields or claim that the live Groq/Ollama/Textual run succeeded.
