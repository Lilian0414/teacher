# proactive-practice Specification

## Purpose
Let Teacher offer timely, low-pressure practice while its terminal UI is open, with deterministic
eligibility and user-controlled suppression that never spends LLM tokens merely to interrupt.
## Requirements
### Requirement: Core determines invitation eligibility and priority
The system SHALL return a proactive practice invitation only when availability is `available`, the
terminal reports that it can present an invitation, the applicable idle threshold has elapsed, and
no persisted cooldown, same-day dismissal, or daily delivery limit blocks it. When one or more
learning items are due, the system SHALL offer review before conversation practice. When none are
due, it SHALL be able to offer a deterministic lightweight English conversation prompt after the
longer conversation idle threshold.

#### Scenario: Due review receives priority
- **WHEN** the terminal is eligible for an invitation and at least one learning item is due
- **THEN** Core returns a review invitation even when conversation practice is also eligible

#### Scenario: Conversation practice is offered without due review
- **WHEN** no learning item is due and the terminal has been presentable and idle for the configured conversation threshold
- **THEN** Core returns a conversation invitation with a locally selected starter prompt

#### Scenario: Busy state suppresses invitations
- **WHEN** availability is `busy` and the terminal checks for an invitation
- **THEN** Core returns no invitation and creates no delivery record

#### Scenario: Do-not-disturb state suppresses invitations
- **WHEN** availability is `dnd` and the terminal checks for an invitation
- **THEN** Core returns no invitation and creates no delivery record

#### Scenario: Active interaction suppresses invitations
- **WHEN** the terminal reports an active review, a help or hint flow, a pending request, or insufficient idle time
- **THEN** Core returns no new invitation

#### Scenario: Eligibility checks do not use the LLM
- **WHEN** the terminal checks for a proactive invitation, whether eligible or suppressed
- **THEN** the system performs no LLM provider request

### Requirement: Invitation delivery is singular, bounded, and persistent
The system SHALL maintain at most one pending invitation for a user. Repeated eligibility checks
SHALL return that same pending invitation instead of creating duplicates. Delivery and response
state SHALL survive application restart, and the system SHALL create no invitations after the
configured local-day delivery limit has been reached.

#### Scenario: Repeated polling reuses a pending invitation
- **WHEN** an invitation is pending and the terminal performs another eligible check
- **THEN** Core returns the same invitation identifier and does not create another delivery

#### Scenario: Restart preserves the pending invitation
- **WHEN** Core restarts after an invitation was delivered but not answered
- **THEN** a later eligible check returns the persisted pending invitation rather than a duplicate

#### Scenario: Daily limit prevents excessive delivery
- **WHEN** the user has already received the configured maximum invitations for the current local date
- **THEN** Core returns no new invitation until the next local date

#### Scenario: Local date uses configured timezone
- **WHEN** invitation state crosses midnight in the configured timezone
- **THEN** same-day dismissal and daily delivery counting use the new configured local date

### Requirement: User can accept, snooze, or dismiss an invitation
The system SHALL accept exactly three user decisions for a pending invitation: start practice,
snooze for the configured interval, or dismiss invitations until the next local date. A decision
SHALL atomically resolve the pending invitation and persist the resulting suppression boundary.

#### Scenario: Starting a review invitation reuses the due review flow
- **WHEN** the user starts a pending review invitation and a learning item remains due
- **THEN** Core marks the invitation accepted and returns the first due review question without recording an attempt

#### Scenario: Due review changed before acceptance
- **WHEN** the user starts a pending review invitation after no learning item remains due
- **THEN** Core resolves the stale invitation without creating an attempt and reports that review is complete

#### Scenario: Starting conversation practice returns a local prompt
- **WHEN** the user starts a pending conversation invitation with an active conversation owned by the configured user
- **THEN** Core atomically marks it accepted, binds that conversation identifier, and returns its persisted deterministic English starter prompt without calling the LLM

#### Scenario: Conversation start requires an owned conversation
- **WHEN** the user starts a pending conversation invitation without a conversation identifier or with another user's conversation
- **THEN** Core rejects the request without changing the invitation from pending

#### Scenario: Snoozing records a suppression boundary
- **WHEN** the user snoozes a pending invitation
- **THEN** Core resolves it and returns no new invitation before the configured snooze boundary

#### Scenario: Dismissing suppresses the remainder of the local day
- **WHEN** the user dismisses a pending invitation for today
- **THEN** Core resolves it and returns no new invitation before the next midnight in the configured timezone

#### Scenario: Invalid or already resolved invitation is rejected safely
- **WHEN** the user responds to an unknown invitation or responds again to a resolved invitation
- **THEN** Core returns a controlled not-found or conflict response without changing other invitation state

### Requirement: Accepted conversation practice joins normal chat
After a conversation invitation is accepted, the terminal SHALL show the returned starter prompt
as a practice invitation and SHALL submit the user's next ordinary response through the existing
conversation message flow. The proactive prompt SHALL NOT be written as a user message, learning
item, or life memory, and an LLM request SHALL occur only after the user submits a chat response.

#### Scenario: Acceptance alone spends no LLM request
- **WHEN** the user accepts a conversation invitation but has not answered its starter prompt
- **THEN** the terminal displays the prompt and the system performs no LLM provider request

#### Scenario: User response uses existing conversation behavior
- **WHEN** the user answers an accepted conversation starter with ordinary text
- **THEN** the terminal sends that text through the current conversation endpoint and displays the normal assistant reply

#### Scenario: Starter is not learning or life memory
- **WHEN** a deterministic conversation starter is delivered or accepted
- **THEN** the starter itself is not inserted into conversation user messages, learning items, or long-term memories

### Requirement: Accepted conversation practice is crash-safe
Conversation practice SHALL follow `pending -> accepted -> completed | abandoned`, while snooze
and same-day dismissal remain the existing suppression branches. An accepted invitation SHALL
prevent another conversation invitation for that user. Before a new conversation session proceeds,
Core SHALL reconcile each stale accepted invitation using only durable messages in its bound
conversation created at or after its acceptance boundary. Exactly one ordered user and assistant
pair SHALL be finalized through the normal practice finalization path; missing, partial, invalid, or
ambiguous evidence SHALL be abandoned and SHALL NOT create a learning occurrence. Reconciliation
and terminal transitions SHALL be idempotent.

#### Scenario: Restart finalizes one attributable turn
- **WHEN** restart reconciliation finds exactly one user message followed by one assistant message in the bound conversation at or after acceptance
- **THEN** Core completes the invitation through normal finalization with those exact evidence identifiers and does not duplicate the result on another reconciliation

#### Scenario: Restart abandons absent or partial evidence
- **WHEN** restart reconciliation finds no post-acceptance answer or only a durable user message
- **THEN** Core marks the invitation abandoned without creating a learning occurrence

#### Scenario: Restart never guesses ambiguous evidence
- **WHEN** restart reconciliation finds multiple possible post-acceptance turns or an invalid conversation binding
- **THEN** Core marks the invitation abandoned without selecting evidence or creating a learning occurrence

#### Scenario: Accepted practice blocks another invitation
- **WHEN** an accepted conversation invitation has not yet reached completed or abandoned
- **THEN** an eligibility check creates and returns no second conversation invitation for that user

### Requirement: Graceful quit resolves active conversation practice
Before ending the conversation or exiting, the terminal SHALL finalize complete pending practice
evidence through Core, or abandon incomplete practice including a pending assistant retry. It SHALL
continue conversation end and memory extraction only after Core confirms a terminal invitation. If
Core cannot confirm completion or abandonment, the terminal SHALL remain open with a recoverable
system message.

#### Scenario: Quit finalizes complete pending evidence
- **WHEN** the user quits with one complete practice user and assistant pair pending finalization
- **THEN** the terminal finalizes those exact identifiers once before ending the conversation

#### Scenario: Quit abandons incomplete or retryable practice
- **WHEN** the user quits before answering or while an assistant reply retry is pending
- **THEN** the terminal abandons the invitation without resending the user message and then ends the conversation normally

#### Scenario: Quit remains open when resolution fails
- **WHEN** Core cannot confirm that active practice is completed or abandoned
- **THEN** the terminal reports a recoverable system error and does not silently exit

### Requirement: Terminal presents invitations without interrupting active work
While running, the terminal SHALL periodically ask Core for invitation eligibility and render a
returned invitation as a distinct non-conversation card with Start, Later, and Not today actions.
It SHALL NOT replace user input, reveal accepted review answers, or interrupt an active review,
help or hint flow, or in-flight request.

#### Scenario: Eligible invitation appears as an action card
- **WHEN** Core returns an invitation while the terminal is in its normal idle state
- **THEN** the terminal displays one invitation card with Start, Later, and Not today actions

#### Scenario: Active workflow remains uninterrupted
- **WHEN** the terminal is reviewing, collecting help or hint input, showing help follow-up actions, or waiting for Core
- **THEN** its eligibility check reports that an invitation cannot be presented and no invitation card replaces the workflow

#### Scenario: Start opens the selected practice flow
- **WHEN** the user chooses Start on an invitation card
- **THEN** the terminal removes the card and enters review mode or displays the conversation starter according to the Core response

#### Scenario: Later and Not today remove the card
- **WHEN** the user chooses Later or Not today on an invitation card
- **THEN** the terminal removes the card after Core confirms the persisted decision

#### Scenario: Core failure does not break the terminal
- **WHEN** an invitation check or decision request fails
- **THEN** the terminal keeps the current conversation and interaction state usable and shows at most a controlled system error
