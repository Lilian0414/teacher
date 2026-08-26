## Purpose

Turn language assistance into persistent, deterministic practice that can be reviewed one item
at a time and can gently shape later English conversation without becoming life memory.
## Requirements
### Requirement: Successful language assistance creates a learning item
The system SHALL create or update a learning item after a successful `/help` or `/hint` command.
The item SHALL retain the user's prompt, one or more accepted English answers derived from the
language-assistance result, its source command, and review scheduling state. `/say` SHALL NOT
create a learning item.

#### Scenario: Chinese help creates an immediately due item
- **WHEN** `/help` successfully returns a natural expression for Chinese input
- **THEN** the system stores the input as the review prompt, stores the natural expression and alternatives as accepted answers, and makes the item due for review immediately

#### Scenario: English help preserves a usable answer
- **WHEN** `/help` successfully analyzes English input
- **THEN** the system stores the correction when one exists, otherwise the original English input, as an accepted answer

#### Scenario: Hint creates an item from phrases
- **WHEN** `/hint` successfully returns one or more keywords, phrases, or patterns
- **THEN** the system stores the input as the review prompt and each returned hint as an accepted answer

#### Scenario: Assistance with no reviewable answer is not stored
- **WHEN** `/help` or `/hint` succeeds but returns no English expression, correction, original English answer, or hint that can be reviewed
- **THEN** the command result remains available but no learning item is created

#### Scenario: Say does not create a learning item
- **WHEN** `/say` successfully translates and inserts English into a conversation
- **THEN** the system does not create or update a learning item

### Requirement: Learning items are deduplicated and persisted
The system SHALL maintain at most one active learning item for the same user, normalized prompt,
and learning kind. Repeated assistance SHALL merge newly returned accepted answers into that item,
record the latest source command, and make the item due no later than the current time. Learning
items and attempts SHALL remain available after application restart.
Accepted answers and review scheduling state SHALL belong only to that kind-specific item.

#### Scenario: Repeated assistance updates rather than duplicates
- **WHEN** the same user requests reviewable assistance again for an equivalent prompt and learning kind after case, whitespace, and terminal punctuation normalization
- **THEN** the existing item is updated and no second active item is created

#### Scenario: Different kinds remain distinct
- **WHEN** the same normalized prompt produces a full-expression item through `/help` and a phrase item through `/hint`
- **THEN** the system retains one item for each learning kind with isolated accepted answers, attempts, stage, and next-review time

#### Scenario: Legacy item identity is expanded without invented history
- **WHEN** a database with prompt-only uniqueness is migrated to kind-aware identity
- **THEN** each existing item keeps its identifier, stored kind, accepted answers, attempts, occurrences, stage, and next-review time, and a later capture of another kind creates a separate item without retroactively splitting the legacy item

#### Scenario: Restart preserves learning state
- **WHEN** the application restarts after learning items or attempts have been committed
- **THEN** the items, attempt history, review stage, and next-review time remain available

### Requirement: Review is an interactive one-question-at-a-time session
The `/review` command SHALL start an interactive terminal session over currently due learning
items, ordered by earliest next-review time and then stable creation order. The system SHALL show
only one prompt at a time. While a review item is active, ordinary non-command terminal input SHALL
be submitted as that item's answer instead of as a conversation message.

#### Scenario: Starting review presents the first due item
- **WHEN** the user enters `/review` and at least one item is due at the current time
- **THEN** the system returns the first item's identifier, prompt, kind, and position without revealing accepted answers

#### Scenario: Starting review with no due items
- **WHEN** the user enters `/review` and no item is due
- **THEN** the system reports that review is complete and does not enter review mode

#### Scenario: Answer advances to the next due item
- **WHEN** the terminal submits a non-empty answer for the active item
- **THEN** the system records exactly one attempt, returns the result and accepted answers, and returns the next due item if one exists

#### Scenario: Final answer completes the session
- **WHEN** an answer is recorded and no other item remains due
- **THEN** the system reports completion and the terminal leaves review mode

#### Scenario: User exits review without answering
- **WHEN** the user enters `/review quit` while an item is active
- **THEN** the terminal leaves review mode without creating an attempt or changing that item's schedule

#### Scenario: Commands remain available during review
- **WHEN** the user enters a slash command other than the review exit command while an item is active
- **THEN** the terminal executes that command normally and keeps the unanswered review item active

#### Scenario: Interrupted review can be resumed
- **WHEN** the application closes with an unanswered review item and the user later enters `/review`
- **THEN** previously recorded attempts remain applied and the still-due unanswered item is eligible to be presented again

### Requirement: Answer evaluation is deterministic and local
The system SHALL evaluate an answer against the saved accepted answers without an LLM request.
Comparison SHALL ignore letter case, repeated whitespace, surrounding whitespace, and terminal
sentence punctuation. A phrase-learning answer SHALL be correct when it equals any accepted phrase;
an expression-learning answer SHALL be correct when it equals any accepted expression.

#### Scenario: Normalized answer is accepted
- **WHEN** the submitted answer differs from an accepted answer only by case, whitespace, or terminal sentence punctuation
- **THEN** the attempt is recorded as correct

#### Scenario: Different answer is rejected
- **WHEN** the normalized submitted answer does not equal any normalized accepted answer
- **THEN** the attempt is recorded as incorrect and the response reveals the accepted answers for learning feedback

### Requirement: Review results advance a simple deterministic schedule
Each learning item SHALL have a zero-based review stage. A correct attempt SHALL advance the stage
by one and schedule the item after 1, 3, 7, 14, or 30 days for stages one through five and every
later stage. An incorrect attempt SHALL reset the stage to zero and schedule the item for one day
later. All calculations SHALL use the injected application clock.

#### Scenario: First correct answer schedules tomorrow
- **WHEN** a due item at stage zero is answered correctly
- **THEN** its stage becomes one and its next-review time is exactly one day after the attempt

#### Scenario: Later correct answers use increasing intervals
- **WHEN** an item at stages one through four is answered correctly
- **THEN** its stage increases by one and its next-review time uses the corresponding 3, 7, 14, or 30 day interval

#### Scenario: Correct mature item remains on thirty-day interval
- **WHEN** an item at stage five or later is answered correctly
- **THEN** its stage increases by one and its next-review time is thirty days after the attempt

#### Scenario: Incorrect answer resets scheduling
- **WHEN** any due item is answered incorrectly
- **THEN** its stage becomes zero and its next-review time is exactly one day after the attempt

### Requirement: Due learning goals influence conversation context
For a normal conversation reply, the system SHALL be able to provide the language model with a
small deterministic set of due learning goals together with a separately labelled set of relevant,
active life memories. Learning prompts and answers SHALL NOT be written to long-term life memory.

#### Scenario: Due goal and relevant life memory are both available
- **WHEN** a user message has at least one due learning item and at least one relevant active life memory
- **THEN** the language-model context contains separately labelled learning and life-memory sections within their configured limits

#### Scenario: Learning data stays out of life memory
- **WHEN** `/help` or `/hint` creates or updates a learning item
- **THEN** neither its prompt nor accepted answers are inserted into the long-term memory tables

#### Scenario: No due goals leaves learning context absent
- **WHEN** no learning item is due at the current time
- **THEN** no learning-goal section is added to the conversation context

### Requirement: Due item count is available without starting a review session
The system SHALL be able to report the number of learning items currently due for the active user
without starting an interactive review session and without revealing item content.

#### Scenario: Count reflects items due at the current time
- **WHEN** the client requests the current due-item count and one or more learning items are due at
  the current time
- **THEN** the system returns the number of due items without returning their prompts or accepted
  answers

#### Scenario: Count is zero when nothing is due
- **WHEN** the client requests the current due-item count and no learning item is due at the current
  time
- **THEN** the system returns zero

#### Scenario: Requesting the count does not start a review session
- **WHEN** the client requests the current due-item count
- **THEN** no review item is marked as active and no attempt is recorded
