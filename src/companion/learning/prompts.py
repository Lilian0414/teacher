import json

from companion.learning.schemas import LearningSignalRequest

LEARNING_SIGNAL_SYSTEM_PROMPT = """Identify at most one concrete English learning point from
the completed turn. Return JSON with a `candidate` object or null. A candidate must contain only:
source_conversation_id, source_user_message_id, source_assistant_message_id, kind (`expression` or
`phrase`), review_prompt, accepted_answers (one to three strings), and reason (`correction`,
`vocabulary`, or `useful_expression`). Copy all source IDs exactly. Greetings and ordinary
chitchat have no candidate. Never propose mastery, stage, scheduling, intervals, or due state."""


def learning_signal_user_prompt(request: LearningSignalRequest) -> str:
    return json.dumps(request.model_dump(), ensure_ascii=False)
