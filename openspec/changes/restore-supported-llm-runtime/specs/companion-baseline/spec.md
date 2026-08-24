# Companion Baseline Specification Delta

## ADDED Requirements

### Requirement: Ship a usable configured LLM contract

The system SHALL ship a currently supported default Groq model and SHALL keep every existing
domain-shaped LLM task verifiable through an explicitly enabled live contract suite.

#### Scenario: Start from fresh supported configuration

- **WHEN** a user configures a valid Groq API key and keeps the documented default model
- **THEN** normal conversation can obtain an assistant response from a supported model
- **AND** runtime status does not claim verified usability based only on key presence

#### Scenario: Exercise structured domain tasks

- **WHEN** the opt-in live contract suite is run with valid credentials
- **THEN** Help, Hint, Say, explicit memory analysis, and conversation memory extraction satisfy
  their existing structured response contracts
- **AND** assertions depend on domain invariants rather than exact provider wording

#### Scenario: Reject an unusable or malformed provider result

- **WHEN** Groq rejects the configured model or returns malformed structured output
- **THEN** the provider boundary reports a controlled error
- **AND** malformed output is not treated as a valid language or memory result

## MODIFIED Requirements

### Requirement: Preserve provider and secret boundaries

The system SHALL use fake providers for ordinary automated tests and SHALL access Groq only through
explicitly enabled live contract tests with caller-supplied credentials.

#### Scenario: Run ordinary validation

- **WHEN** Ruff, mypy, and pytest are run without the live-test opt-in
- **THEN** no real Groq request is made
- **AND** no API key appears in code, logs, test output, or Git

#### Scenario: Run explicit provider contract validation

- **WHEN** the live-test opt-in and API key are both supplied
- **THEN** the suite may call Groq only for the existing domain contract checks
- **AND** failures identify the affected contract without disclosing the credential or full private
  conversation content

