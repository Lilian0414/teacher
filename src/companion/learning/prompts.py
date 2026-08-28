import json

from companion.learning.schemas import LearningSignalRequest

LEARNING_SIGNAL_SYSTEM_PROMPT = """Inspect the learner's completed turn for concrete English error
evidence, then select at most one high-value learning point. Return JSON with exactly `observation`
and `candidate`. `observation` must contain error_type (`spelling`, `verb_tense`, `subject_verb`,
`word_choice`, `other_correction`, or `none`), source_excerpt, correction, and confidence (`high`,
`medium`, or `low`). For an error, copy source_excerpt exactly from user_content and give a
materially different correction. Otherwise use error_type `none` and empty
source_excerpt/correction.

Use this strict one-item priority: high-confidence learner correction > high-value vocabulary or
word-choice gap > useful expression > null. Do not capture every typo, ambiguous/style-only edits,
proper names, brands, URLs, harmless informal English, or ordinary chitchat. When a clear correction
is observed at high confidence, candidate should express that correction. `candidate=null` is better
than a weak, noisy, or context-dependent item. A candidate must contain only:
source_conversation_id, source_user_message_id, source_assistant_message_id, kind (`expression` or
`phrase`), review_prompt, accepted_answers (one to three strings), and reason (`correction`,
`vocabulary`, or `useful_expression`).

The review_prompt must be a standalone, future-facing question that makes sense with no transcript.
Never rely on references such as "the user's sentence", "above", "previous", or "this/that
sentence/phrase/word" unless the prompt itself explicitly includes the source text needed to answer.
For spelling and correction items, include the actual misspelling or token, or a sufficient quoted
source sentence. Keep accepted_answers short and direct for deterministic exact/normalized grading;
provide only one to three answers.

Copy all source IDs exactly. Greetings and ordinary chitchat have no candidate. Never propose
mastery, stage, scheduling, intervals, due state, or any other scheduling metadata."""


def learning_signal_user_prompt(request: LearningSignalRequest) -> str:
    return json.dumps(request.model_dump(), ensure_ascii=False)
