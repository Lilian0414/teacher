import json

from companion.memory.schemas import MemoryAnalysisRequest, MemoryExtractionRequest

MEMORY_CATEGORIES = (
    "people, personal, school_work, relationships, health_fitness, other"
)

ANALYSIS_SYSTEM_PROMPT = f"""Classify a memory the user explicitly asked to save.
Do not rewrite, infer, correct, or add facts. Choose one category from: {MEMORY_CATEGORIES}.
Extract a person only when a named person is clearly involved. Preserve exact names.
Return JSON only:
{{"category": string, "person_name": string|null, "aliases": [string],
"relationship_to_user": string|null, "confidence": number|null}}.
"""

EXTRACTION_SYSTEM_PROMPT = f"""You extract long-term memories from a conversation.

Save only explicit information that could be useful in a future conversation.
Do not infer facts that were not stated.
Do not save greetings, temporary wording, assistant messages, or trivial details.
Preserve names, relationships, uncertainty, and time references.
If information updates an earlier fact, set updates_memory_id instead of creating a duplicate.
Choose one category from: {MEMORY_CATEGORIES}.

Return only structured JSON matching this schema:
{{"candidates": [{{"category": string, "content": string, "person_name": string|null,
"aliases": [string], "relationship_to_user": string|null, "confidence": number|null,
"source_message_ids": [string], "updates_memory_id": string|null}}]}}.
Return {{"candidates": []}} when there is nothing worth saving.
"""

MEMORY_CONTEXT_SYSTEM_PROMPT = """The following memories may be relevant to the conversation.
Use them only when they are clearly relevant.
Do not claim uncertain memories as confirmed facts.
Do not reveal internal memory IDs, categories, confidence values, or implementation details.
If memories conflict, ask the user instead of choosing one.
"""


def analysis_user_prompt(request: MemoryAnalysisRequest) -> str:
    return f"MEMORY\n{request.content}"


def extraction_user_prompt(request: MemoryExtractionRequest) -> str:
    existing = [item.model_dump(mode="json") for item in request.existing_memories]
    messages = [item.model_dump(mode="json") for item in request.messages]
    return (
        "EXISTING MEMORIES\n"
        + json.dumps(existing, ensure_ascii=False)
        + "\n\nCONVERSATION USER MESSAGES\n"
        + json.dumps(messages, ensure_ascii=False)
    )


def memory_context_prompt(contents: list[str]) -> str:
    return MEMORY_CONTEXT_SYSTEM_PROMPT + "\nMEMORIES\n" + json.dumps(
        contents,
        ensure_ascii=False,
    )
