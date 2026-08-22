import math
import re

from companion.memory.prompts import memory_context_prompt
from companion.memory.repository import MemoryRepository
from companion.memory.schemas import MemoryCategory, MemorySchema, MemoryStatus
from companion.persistence.models import Memory
from companion.persistence.repositories import decode_dt
from companion.providers.embeddings import EmbeddingProvider, normalize_embedding

WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SEMANTIC_WEIGHT = 8.0
MIN_SEMANTIC_SIMILARITY = 0.35


class MemoryContextBuilder:
    def __init__(
        self,
        repository: MemoryRepository,
        *,
        limit: int = 5,
        embedding_provider: EmbeddingProvider | None = None,
        candidate_limit: int = 200,
    ) -> None:
        self._repository = repository
        self._limit = limit
        self._embedding_provider = embedding_provider
        self._candidate_limit = candidate_limit

    def select(self, current_message: str) -> list[MemorySchema]:
        query_embedding = self._embed(current_message)
        ranked: list[tuple[float, MemorySchema]] = []
        for memory in self._repository.list_memories(limit=self._candidate_limit):
            schema = memory_to_schema(memory, self._repository)
            score = hybrid_relevance_score(
                current_message,
                schema,
                query_embedding=query_embedding,
                memory_embedding=self._repository.decode_embedding(memory),
            )
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

    def _embed(self, text: str) -> list[float] | None:
        if self._embedding_provider is None:
            return None
        try:
            return normalize_embedding(self._embedding_provider.embed(text))
        except Exception:
            # Recall must remain available through lexical/person signals when a
            # configured provider is temporarily unavailable.
            return None


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


def hybrid_relevance_score(
    query: str,
    memory: MemorySchema,
    *,
    query_embedding: list[float] | None,
    memory_embedding: list[float] | None,
) -> float:
    lexical_person_score = float(relevance_score(query, memory))
    similarity = cosine_similarity(query_embedding, memory_embedding)
    semantic_score = (
        similarity * SEMANTIC_WEIGHT if similarity >= MIN_SEMANTIC_SIMILARITY else 0.0
    )
    return lexical_person_score + semantic_score


def cosine_similarity(
    first: list[float] | None,
    second: list[float] | None,
) -> float:
    if first is None or second is None or len(first) != len(second) or not first:
        return 0.0
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if first_norm == 0.0 or second_norm == 0.0:
        return 0.0
    return sum(left * right for left, right in zip(first, second, strict=True)) / (
        first_norm * second_norm
    )


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
