# companion-baseline Specification

## Purpose
TBD - created by archiving change reconcile-m2-baseline. Update Purpose after archive.
## Requirements
### Requirement: Deterministic availability controls

The system SHALL support `available`, `busy`, and `dnd` availability states through deterministic commands, without asking an LLM to interpret command names or durations.

#### Scenario: Temporarily busy

- **WHEN** the user executes `/busy <duration>`
- **THEN** the system stores a busy override with an expiration
- **AND** later state reads expose the remaining time

#### Scenario: Indefinite DND and recovery

- **WHEN** the user executes `/dnd` and later `/available`
- **THEN** the system first blocks availability indefinitely and then clears the override

### Requirement: Persisted English text conversation

The system SHALL create text conversations, persist user and assistant messages in SQLite, and send only a bounded recent context to the configured LLM provider.

#### Scenario: Continue a conversation

- **WHEN** the user sends English text to a valid conversation
- **THEN** both the user message and assistant response are persisted
- **AND** a provider failure is returned as an error rather than an assistant message

### Requirement: Distinct language rescue commands

The system SHALL expose exactly three M1 language commands with non-overlapping effects: `/help`, `/hint`, and `/say`.

#### Scenario: Learn without sending

- **WHEN** the user invokes `/help <content>`
- **THEN** the system provides expression help or an English explanation
- **AND** does not insert the result into the conversation

#### Scenario: Receive partial hints

- **WHEN** the user invokes `/hint <content>`
- **THEN** the system returns one to three words, phrases, or incomplete patterns
- **AND** does not provide a complete translated answer or insert a message

#### Scenario: Translate and continue

- **WHEN** the user invokes `/say <Chinese>` with a valid conversation ID
- **THEN** the system translates one natural utterance
- **AND** stores it as a user message
- **AND** obtains the normal assistant reply

### Requirement: Manage simple long-term memories

The system SHALL store long-term memories using the categories `people`, `personal`, `school_work`, `relationships`, `health_fitness`, and `other`, with statuses limited to `active` and `deleted`.

#### Scenario: Explicitly remember and search

- **WHEN** the user invokes `/remember <content>`
- **THEN** the original meaning is stored as an active memory
- **AND** `/memories [query]` can retrieve matching active memories

#### Scenario: Confirm before forgetting

- **WHEN** the user invokes `/forget <memory_id>`
- **THEN** the system previews the target without deleting it
- **AND WHEN** the user repeats it with `confirm`
- **THEN** the memory is soft-deleted and excluded from normal search and recall

### Requirement: Extract memories under deterministic policy

The system SHALL request memory candidates when a conversation ends while applying deterministic validation before persistence.

#### Scenario: Accept a valid user fact

- **WHEN** a candidate cites only valid user-message IDs and is not trivial or duplicated
- **THEN** the system creates or updates the corresponding memory

#### Scenario: Reject unsupported content

- **WHEN** a candidate cites an assistant message, an unknown source ID, or only a trivial greeting
- **THEN** the system skips it without persisting a memory

#### Scenario: Provider extraction failure

- **WHEN** memory extraction fails at the provider boundary
- **THEN** the conversation remains ended
- **AND** the extraction result reports a controlled error

### Requirement: Recall only a small relevant memory set

The system SHALL select at most five active memories using name and text relevance and inject only those memories into normal chat context.

#### Scenario: Ask about a known person

- **WHEN** the user message names a person with stored active memories
- **THEN** matching memories are preferred
- **AND** unrelated or deleted memories are excluded
- **AND** internal memory IDs are not disclosed to the model as conversational facts

### Requirement: Preserve provider and secret boundaries

The system SHALL use fake providers for automated tests and SHALL access Groq only through explicitly enabled live tests.

#### Scenario: Run ordinary validation

- **WHEN** Ruff, mypy, and pytest are run without the live-test opt-in
- **THEN** no real Groq request is made
- **AND** no API key appears in code, logs, test output, or Git

