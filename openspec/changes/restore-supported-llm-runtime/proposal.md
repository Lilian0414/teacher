# Change: Restore a supported LLM runtime

## Why

Teacher's fresh Groq configuration defaults to `llama-3.1-8b-instant`, which Groq shut down for
the free/developer tier on 2026-08-16. A valid API key therefore cannot run normal conversation,
language rescue commands, explicit memory analysis, or conversation-end memory extraction.
Ordinary CI does not catch this because real-provider tests are intentionally opt-in.

## What Changes

- Replace the retired default with a currently supported Groq model that satisfies every existing
  text and structured-output contract.
- Align `.env.example` and user-facing documentation with the supported default.
- Make the opt-in Groq contract suite exercise normal chat, Help, Hint, Say, explicit memory
  analysis, and conversation memory extraction.
- Keep ordinary tests deterministic and offline, and keep runtime status wording honest about the
  difference between key presence and verified model usability.
- Preserve existing controlled error and persistence behavior when Groq rejects a request or
  returns malformed structured output.

## Non-goals

- No learning-loop, memory-policy, grading, proactive-practice, or database changes.
- No new LLM provider abstraction, routing framework, fallback provider, or model-selection UI.
- No Japanese support or teacher-personality work.
- No API keys, captured live responses, or other credentials in Git.

## Measurable Outcome

A fresh documented Groq setup points to a supported model. With explicitly supplied live-test
credentials, one opt-in contract suite can verify every existing LLM task. Without that opt-in,
Ruff, strict mypy, and the complete ordinary pytest suite make no network request and remain green.

