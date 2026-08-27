import json

from companion.learning.schemas import LearningSignalRequest

LEARNING_SIGNAL_SYSTEM_PROMPT = """Identify at most one concrete, high-value English learning
point from the completed turn. Return JSON with a `candidate` object or null. `candidate=null` is
better than a weak, noisy, or context-dependent item. A candidate must contain only:
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
