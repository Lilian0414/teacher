## Context

See `proposal.md` for motivation and `specs/proactive-practice/spec.md` for observable behavior.
Teacher currently polls `/v1/state` every five seconds, keeps transient interaction and review state
inside the Textual process, and places deterministic time policy behind an injectable application
clock. Learning due times and availability are already Core-owned and persisted in SQLite.

M4 crosses API, persistence, learning, availability, settings, and terminal UI boundaries. It must
remain useful with `FakeLLMProvider`, avoid background macOS processes, and never generate paid
traffic simply because a timer fired.

## Goals / Non-Goals

**Goals:**

- Make invitation eligibility deterministic, testable with a fake clock, and authoritative in Core.
- Use UI-reported presentation and idle facts without moving scheduling thresholds into Textual.
- Reuse the existing review and conversation paths after acceptance.
- Persist enough history to enforce one-pending, cooldown, dismissal, and daily-limit behavior
  across restarts.
- Add no runtime dependency beyond the existing stack.

**Non-Goals:**

- A continuously running scheduler, launch agent, menu-bar process, or macOS notification.
- LLM-generated invitation copy or prompts.
- A new review cursor, separate conversation mode, user-configurable settings screen, or multi-user
  synchronization.
- Recording a dismissed invitation as a learning attempt or conversation message.

## Decisions

### 1. Evaluate eligibility on an explicit Core check, not a background job

Add `POST /v1/proactive/check`. Textual calls it on a low-frequency interval and supplies only
transient UI facts such as `idle_seconds` and `can_present`. `ProactiveService` combines those facts
with the injected clock, availability snapshot, due learning count, settings, and persisted history.

This keeps all policy and wall-clock thresholds in Core while avoiding APScheduler, threads, or a
process that cannot help after the terminal closes. A pure `GET` was rejected because eligibility
depends on an explicit UI-state input; embedding proactive state into the existing five-second
`/v1/state` request was rejected because it would create delivery records during status refreshes
that are not prepared to display an invitation.

### 2. Persist each delivered invitation as the policy ledger

Add a `proactive_invitations` table with:

- UUID `id`, indexed `user_id`, `kind` (`review` or `conversation`), and `status` (`pending`,
  `accepted`, `snoozed`, `dismissed`, or `expired`)
- timezone-aware encoded `created_at`, optional `responded_at`, and optional `suppress_until`
- `local_date` for deterministic daily counting
- optional `starter_key` and `starter_prompt` for conversation invitations

The repository returns the current pending row, counts deliveries by local date, and resolves a
pending row with an expected-status update so repeated decision requests cannot both win. The
service expires a stale pending invitation only when its kind can no longer be acted on safely;
otherwise polling returns the same row. A separate mutable preferences table was rejected because
the invitation ledger already supplies the required boundaries and makes behavior auditable.

### 3. Use settings for thresholds, with conservative defaults

Add validated settings for poll interval, review idle threshold, conversation idle threshold,
snooze interval, post-accept cooldown, and daily delivery limit. Proposed defaults are 30 seconds,
10 minutes, 30 minutes, 30 minutes, 60 minutes, and 3 invitations per local date. Tests override
settings and inject time; documentation shows how to shorten thresholds for a demo.

`idle_seconds` resets in Textual after input submission, button actions, and completed invitation
decisions. Core compares it with the kind-specific threshold. Trusting this local UI measurement is
acceptable for the single-user local application; persisting high-frequency heartbeats would add
write load without improving the user experience.

### 4. Choose conversation starters locally and persist the selection

Core rotates through a small fixed tuple of English prompts using the count of prior conversation
invitations for the local date. The selected key and text are stored with the invitation, so repeat
polls and restarts cannot change it. Accepting the invitation returns that text and performs no LLM
request. The next ordinary user input continues through the existing conversation endpoint.

Generating the starter with Groq was rejected because it would spend tokens before consent and
would make scheduler tests nondeterministic. Creating an assistant conversation message at delivery
was rejected because an ignored card should not contaminate conversation history or later memory
extraction.

### 5. Reuse review service semantics at acceptance time

`POST /v1/proactive/invitations/{id}/respond` accepts `start`, `snooze`, or `dismiss_today`.
For `start` on a review invitation, the route resolves the invitation and then asks the existing
`LearningService.first_due()` for the current question. It never creates an attempt. If the due set
changed, the response reports review complete instead of resurrecting stale work.

The decision response is a tagged schema containing the resolved invitation plus either a review
question or a conversation starter. The terminal maps the review question into its existing
`_active_review_item_id` flow and maps the conversation starter into a small transient
`PRACTICE_PROMPT` mode whose next ordinary input already uses normal chat.

### 6. Render invitations as UI state, not transcript content

Textual gets a dedicated invitation container and three reusable action buttons. A card is shown
only in normal, non-waiting, non-review state. Help, hint, help-result, and review modes set
`can_present=false`. Availability suppression remains authoritative in Core even if Textual reports
incorrectly.

Invitation checks are guarded so failures do not disable input. Decision failures keep the card
available for retry and display one controlled system line; successful decisions remove it.

## Risks / Trade-offs

- [Polling can deliver slightly after a threshold] → Return the next eligible boundary and keep the
  interval configurable; second-level precision is not a product requirement.
- [A pending card may become stale as learning state changes] → Re-evaluate review availability on
  Start and return review complete safely.
- [The fixed prompt list can feel repetitive] → Rotate deterministically and keep the list isolated
  for later expansion without changing persistence or API contracts.
- [UI-reported idle time resets on restart] → Persist decisions and pending deliveries, but accept a
  fresh idle grace period after restart to avoid an immediate new interruption.
- [SQLite cannot express a portable partial unique constraint through current patterns] → Use an
  indexed status query plus expected-status updates inside one transaction; the single-process M4
  runtime remains the supported deployment.

## Migration Plan

1. Add the invitation model and Alembic migration after revision `20260810_0004`.
2. Deploy Core and run `alembic upgrade head` before starting the updated terminal UI.
3. Existing users begin with no delivery history; no M0–M3 data is transformed.
4. Rollback first stops the updated UI, then downgrades one revision to drop only the new table.

