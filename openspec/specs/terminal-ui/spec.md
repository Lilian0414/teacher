# terminal-ui Specification

## Purpose
Give the terminal a learning-product interaction model — intent-based entry points and readable
output — instead of requiring the user to know internal slash-command names and reading
implementation-oriented debug labels.
## Requirements
### Requirement: Primary learning intents are reachable without slash commands
The terminal SHALL expose Help me say it, Give me a hint, and Review as on-screen actions reachable
by button press or keyboard shortcut, without requiring the user to type `/help`, `/hint`, or
`/review`.

#### Scenario: New user reaches help without typing a command
- **WHEN** the user activates "Help me say it" through its button or keyboard shortcut
- **THEN** the terminal prompts for a sentence and, once provided, produces the same result the
  `/help` command would produce for that sentence

#### Scenario: New user reaches a hint without typing a command
- **WHEN** the user activates "Give me a hint" through its button or keyboard shortcut
- **THEN** the terminal prompts for a sentence and, once provided, produces the same result the
  `/hint` command would produce for that sentence

#### Scenario: New user starts a review without typing a command
- **WHEN** the user activates "Review" through its button or keyboard shortcut
- **THEN** the terminal starts the same review session `/review` would start

### Requirement: Help me say it offers a clear choice between teaching, hinting, and sending
After a successful Help me say it response, the terminal SHALL offer exactly three follow-up
actions: Use this, Hint only, and Try myself. Use this SHALL reuse the existing `/say` command
execution path and continue the conversation. Hint only SHALL reuse the existing `/hint` command
execution path for the same sentence instead of sending anything. Try myself SHALL return focus to
normal input without sending or inserting the suggested sentence.

#### Scenario: Use this sends the suggestion and continues the conversation
- **WHEN** the user selects "Use this" after a Help me say it response
- **THEN** the terminal dispatches through the existing `/say` command path with the originally
  captured sentence and displays the resulting assistant reply

#### Scenario: Hint only does not send the suggestion
- **WHEN** the user selects "Hint only" after a Help me say it response
- **THEN** the terminal dispatches through the existing `/hint` command path with the originally
  captured sentence and does not insert anything into the conversation

#### Scenario: Try myself sends nothing
- **WHEN** the user selects "Try myself" after a Help me say it response
- **THEN** the terminal returns to normal input mode without sending or inserting the suggested
  sentence, and without creating a network request beyond the original Help me say it call

### Requirement: Command output uses structured, readable presentation
The terminal SHALL NOT render implementation-oriented labels (`[help]`, `[help alt]`, `[help zh]`,
`[help correction]`, `[say] inserted`, or bracketed review-item prefixes) in normal command output.
Help results SHALL be presented under readable headings such as "Natural expression", "Alternative",
and "Note".

#### Scenario: Help output has no debug prefixes
- **WHEN** a `/help` (or Help me say it) response includes a natural expression, an alternative, and
  a note
- **THEN** the rendered output contains none of `[help]`, `[help alt]`, `[help zh]`, or
  `[help correction]`

#### Scenario: Say output has no debug prefix
- **WHEN** a `/say` (or Use this) response inserts a translated sentence
- **THEN** the rendered output does not contain `[say] inserted`

### Requirement: Due review items are discoverable without starting a review session
The terminal SHALL display a passive indicator of how many learning items are currently due,
updated on its existing periodic state refresh, without starting a review session or sending a
proactive message into the conversation log.

#### Scenario: Status bar reflects pending review items
- **WHEN** the terminal's periodic state refresh reports one or more due learning items
- **THEN** the status bar displays the current due-item count without the terminal entering review
  mode

#### Scenario: Status bar reflects no pending review items
- **WHEN** the terminal's periodic state refresh reports zero due learning items
- **THEN** the status bar indicates that review is up to date

### Requirement: Slash commands remain a supported advanced interface
The terminal SHALL continue to accept `/help`, `/hint`, `/say`, `/review`, `/review quit`,
`/remember`, `/memories`, `/forget`, `/busy`, `/dnd`, `/available`, and `/status` typed directly,
dispatching through the same `/v1/commands/execute` path as before this change.

#### Scenario: A slash command still works after the UI change
- **WHEN** the user types `/help <content>` directly instead of using the Help me say it button
- **THEN** the terminal dispatches it through `/v1/commands/execute` exactly as it did before this
  change

