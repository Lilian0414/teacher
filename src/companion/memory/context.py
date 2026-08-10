import re

from companion.memory.prompts import memory_context_prompt
from companion.memory.repository import MemoryRepository
from companion.memory.schemas import MemoryCategory, MemorySchema, MemoryStatus
from companion.persistence.models import Memory
from companion.persistence.repositories import decode_dt

WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class MemoryContextBuilder:
    def __init__(self, repository: MemoryRepository, *, limit: int = 5) -> None:
        self._repository = repository
        self._limit = limit

    def select(self, current_message: str) -> list[MemorySchema]:
        ranked: list[tuple[int, MemorySchema]] = []
        for memory in self._repository.list_memories(limit=200):
            schema = memory_to_schema(memory, self._repository)
            score = relevance_score(current_message, schema)
            if score > 0:
                ranked.append((score, schema))
        ranked.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [memory for _, memory in ranked[: self._limit]]

    def build(self, current_message: str) -> str | None:
        selected = self.select(current_message)
        if not selected:
            return None
        contents = [
            (
                f"Possibly outdated or uncertain: {item.content}"
                if _is_uncertain(item)
                else item.content
            )
            for item in selected
        ]
        return memory_context_prompt(contents)


def relevance_score(query: str, memory: MemorySchema) -> int:
    query_folded = query.casefold()
    score = 0
    if memory.person is not None:
        names = [memory.person.canonical_name, *memory.person.aliases]
        if any(name.casefold() in query_folded for name in names if name.strip()):
            score += 10
    query_words = set(WORD_PATTERN.findall(query_folded))
    memory_words = set(WORD_PATTERN.findall(memory.content.casefold()))
    score += len(query_words & memory_words) * 2
    query_bigrams = _cjk_bigrams(query)
    memory_bigrams = _cjk_bigrams(memory.content)
    score += len(query_bigrams & memory_bigrams)
    return score


def memory_to_schema(memory: Memory, repository: MemoryRepository) -> MemorySchema:
    person = repository.get_person(memory.person_id) if memory.person_id else None
    person_schema = None
    if person is not None:
        from companion.memory.schemas import PersonSchema

        person_schema = PersonSchema(
            id=person.id,
            canonical_name=person.canonical_name,
            aliases=repository.decode_aliases(person),
            relationship_to_user=person.relationship_to_user,
        )
    return MemorySchema(
        id=memory.id,
        short_id=memory.id[:8],
        category=MemoryCategory(memory.category),
        content=memory.content,
        person=person_schema,
        source_conversation_id=memory.source_conversation_id,
        confidence=memory.confidence,
        status=MemoryStatus(memory.status),
        created_at=decode_dt(memory.created_at),
        updated_at=decode_dt(memory.updated_at),
    )


def _cjk_bigrams(value: str) -> set[str]:
    characters = [character for character in value if CJK_PATTERN.match(character)]
    return {"".join(characters[index : index + 2]) for index in range(len(characters) - 1)}


def _is_uncertain(memory: MemorySchema) -> bool:
    return memory.confidence is not None and memory.confidence < 0.7
