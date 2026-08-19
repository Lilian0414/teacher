## ADDED Requirements

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
