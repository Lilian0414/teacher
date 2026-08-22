import json
import math
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from companion.memory.errors import AmbiguousMemoryIdError
from companion.memory.schemas import MemoryCategory, MemoryStatus
from companion.persistence.models import Memory, Person
from companion.persistence.repositories import encode_dt


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_person(self, person_id: str) -> Person | None:
        return self._session.get(Person, person_id)

    def get_person_by_name(self, canonical_name: str) -> Person | None:
        statement: Select[tuple[Person]] = select(Person).where(
            Person.canonical_name == canonical_name.strip()
        )
        return self._session.scalar(statement)

    def get_or_create_person(
        self,
        *,
        canonical_name: str,
        aliases: list[str],
        relationship_to_user: str | None,
        now: datetime,
    ) -> Person:
        person = self.get_person_by_name(canonical_name)
        if person is None:
            person = Person(
                id=str(uuid4()),
                canonical_name=canonical_name.strip(),
                aliases=json.dumps(sorted(set(aliases)), ensure_ascii=False),
                relationship_to_user=relationship_to_user,
                created_at=encode_dt(now),
                updated_at=encode_dt(now),
            )
            self._session.add(person)
        else:
            current_aliases = set(self.decode_aliases(person))
            updated_aliases = sorted(current_aliases | set(aliases))
            person.aliases = json.dumps(updated_aliases, ensure_ascii=False)
            if relationship_to_user:
                person.relationship_to_user = relationship_to_user
            person.updated_at = encode_dt(now)
        self._session.commit()
        self._session.refresh(person)
        return person

    def create_memory(
        self,
        *,
        category: MemoryCategory,
        content: str,
        person_id: str | None,
        source_conversation_id: str | None,
        confidence: float | None,
        now: datetime,
        embedding: list[float] | None = None,
    ) -> Memory:
        memory = Memory(
            id=str(uuid4()),
            category=category.value,
            content=content.strip(),
            embedding=self.encode_embedding(embedding),
            person_id=person_id,
            source_conversation_id=source_conversation_id,
            confidence=confidence,
            status=MemoryStatus.ACTIVE.value,
            created_at=encode_dt(now),
            updated_at=encode_dt(now),
        )
        self._session.add(memory)
        self._session.commit()
        self._session.refresh(memory)
        return memory

    def get_memory(self, identifier: str) -> Memory | None:
        exact = self._session.get(Memory, identifier)
        if exact is not None:
            return exact
        statement: Select[tuple[Memory]] = select(Memory).where(
            Memory.id.like(f"{identifier}%")
        )
        matches = list(self._session.scalars(statement))
        if len(matches) > 1:
            raise AmbiguousMemoryIdError(identifier)
        return matches[0] if matches else None

    def list_memories(
        self,
        *,
        query: str | None = None,
        include_deleted: bool = False,
        limit: int = 100,
    ) -> list[Memory]:
        statement: Select[tuple[Memory]] = select(Memory)
        if not include_deleted:
            statement = statement.where(Memory.status == MemoryStatus.ACTIVE.value)
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.outerjoin(Person, Memory.person_id == Person.id).where(
                or_(
                    Memory.content.ilike(pattern),
                    Person.canonical_name.ilike(pattern),
                    Person.aliases.ilike(pattern),
                )
            )
        statement = statement.order_by(Memory.updated_at.desc()).limit(limit)
        return list(self._session.scalars(statement))

    def find_duplicate(
        self,
        *,
        category: MemoryCategory,
        content: str,
        person_id: str | None,
    ) -> Memory | None:
        normalized = normalize_content(content)
        candidates = self.list_memories(limit=500)
        return next(
            (
                memory
                for memory in candidates
                if memory.category == category.value
                and memory.person_id == person_id
                and normalize_content(memory.content) == normalized
            ),
            None,
        )

    def update_memory(
        self,
        memory: Memory,
        *,
        content: str | None,
        category: MemoryCategory | None,
        person_id: str | None,
        source_conversation_id: str | None,
        confidence: float | None,
        now: datetime,
        embedding: list[float] | None = None,
    ) -> Memory:
        if content is not None:
            memory.content = content.strip()
        if content is not None or embedding is not None:
            memory.embedding = self.encode_embedding(embedding)
        if category is not None:
            memory.category = category.value
        if person_id is not None:
            memory.person_id = person_id
        if source_conversation_id is not None:
            memory.source_conversation_id = source_conversation_id
        if confidence is not None:
            memory.confidence = confidence
        memory.status = MemoryStatus.ACTIVE.value
        memory.updated_at = encode_dt(now)
        self._session.commit()
        self._session.refresh(memory)
        return memory

    def soft_delete(self, memory: Memory, *, now: datetime) -> Memory:
        memory.status = MemoryStatus.DELETED.value
        memory.updated_at = encode_dt(now)
        self._session.commit()
        self._session.refresh(memory)
        return memory

    @staticmethod
    def decode_aliases(person: Person) -> list[str]:
        data = json.loads(person.aliases)
        return [str(item) for item in data] if isinstance(data, list) else []

    @staticmethod
    def encode_embedding(embedding: list[float] | None) -> str | None:
        if embedding is None:
            return None
        return json.dumps(embedding, separators=(",", ":"))

    @staticmethod
    def decode_embedding(memory: Memory) -> list[float] | None:
        if memory.embedding is None:
            return None
        try:
            data = json.loads(memory.embedding)
            if not isinstance(data, list):
                return None
            embedding = [float(item) for item in data]
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not embedding or not all(math.isfinite(value) for value in embedding):
            return None
        return embedding


def normalize_content(content: str) -> str:
    return " ".join(content.casefold().split()).rstrip(".!?。！？")
