## 1. Supported model configuration

- [x] 1.1 Confirm a replacement model against current official Groq model/deprecation documentation, then update the validated default and `.env.example`. (Requirement: Ship a usable configured LLM contract)
- [x] 1.2 Update only the user-facing documentation that names the default model or setup behavior; keep model overrides supported and avoid unrelated documentation cleanup. (Requirement: Ship a usable configured LLM contract)

## 2. Provider contract verification

- [x] 2.1 Extend opt-in Groq live coverage to normal chat and all Help, Hint, and Say response contracts without exposing secrets or full provider payloads. (Requirements: Ship a usable configured LLM contract; Preserve provider and secret boundaries)
- [x] 2.2 Extend opt-in Groq live coverage to explicit memory analysis and conversation memory extraction, including schema invariants. (Requirements: Ship a usable configured LLM contract; Preserve provider and secret boundaries)
- [x] 2.3 Verify rejected models and malformed structured responses remain controlled errors and cannot cross an unsafe persistence boundary; add offline fake-provider coverage where the behavior is application-owned. (Requirement: Ship a usable configured LLM contract)

## 3. Status and final validation

- [x] 3.1 Audit runtime status wording so key presence or configuration is not presented as verified model usability; change behavior only where the current wording violates the requirement. (Requirement: Ship a usable configured LLM contract)
- [x] 3.2 Run `ruff check .`, `mypy .`, `pytest`, and `git diff --check`; run the opt-in Groq suite only if credentials are already available, and record exact results or the precise credential blocker. (Requirements: Ship a usable configured LLM contract; Preserve provider and secret boundaries)
- [x] 3.3 Deliver a focused implementation child PR linked to GitHub Issue #28 and the anchored planning PR; do not merge it. (Requirements: all restore-supported-llm-runtime requirements)

