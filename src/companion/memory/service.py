from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from companion.clock import Clock, system_clock
from companion.conversation.repository import ConversationRepository
from companion.memory.context import memory_to_schema
from companion.memory.errors import MemoryError, MemoryNotFoundError, MemoryValidationError
from companion.memory.repository import MemoryRepository
from companion.memory.schemas import (
    ExistingMemory,
    MemoryAnalysis,
    MemoryAnalysisRequest,
    MemoryCandidate,
    MemoryCategory,
    MemoryExtractionMessage,
    MemoryExtractionRequest,
    MemoryExtractionResult,
    MemorySchema,
    MemoryStatus,
)
from companion.persistence.models import Memory
from companion.providers.embeddings import EmbeddingProvider, normalize_embedding
from companion.providers.errors import LLMProviderError
from companion.providers.protocols import LLMProvider
from companion.schemas.conversation import MessageRole


@dataclass(frozen=True)
class ForgetPreview:
    memory: MemorySchema
    confirmation_required: bool


class MemoryService:
    def __init__(
        self,
        *,
        repository: MemoryRepository,
        conversation_repository: ConversationRepository,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider | None = None,
        clock: Clock = system_clock,
    ) -> None:
        self._repository = repository
        self._conversation_repository = conversation_repository
        self._llm_provider = llm_provider
        self._embedding_provider = embedding_provider
        self._clock = clock

    async def remember(self, content: str) -> MemorySchema:
        text = content.strip()
        if not text:
            raise MemoryValidationError("Memory content is required")
        try:
            analysis = await self._llm_provider.analyze_memory(
                MemoryAnalysisRequest(content=text)
            )
        except LLMProviderError:
            analysis = MemoryAnalysis(category=MemoryCategory.OTHER)
        memory, _ = self._store(
            category=analysis.category,
            content=text,
            person_name=analysis.person_name,
            aliases=analysis.aliases,
            relationship_to_user=analysis.relationship_to_user,
            confidence=analysis.confidence,
            source_conversation_id=None,
            updates_memory_id=None,
        )
        return memory_to_schema(memory, self._repository)

    def search(self, query: str | None = None) -> list[MemorySchema]:
        return [
            memory_to_schema(memory, self._repository)
            for memory in self._repository.list_memories(query=query)
        ]

    def get(self, identifier: str) -> MemorySchema:
        memory = self._repository.get_memory(identifier)
        if memory is None or memory.status == MemoryStatus.DELETED.value:
            raise MemoryNotFoundError(identifier)
        return memory_to_schema(memory, self._repository)

    def preview_forget(self, identifier: str) -> ForgetPreview:
        return ForgetPreview(memory=self.get(identifier), confirmation_required=True)

    def forget(self, identifier: str) -> MemorySchema:
        memory = self._repository.get_memory(identifier)
        if memory is None or memory.status == MemoryStatus.DELETED.value:
            raise MemoryNotFoundError(identifier)
        deleted = self._repository.soft_delete(memory, now=self._clock())
        return memory_to_schema(deleted, self._repository)

    async def extract_conversation(self, conversation_id: str) -> MemoryExtractionResult:
        conversation = self._conversation_repository.get_conversation(conversation_id)
        if conversation is None:
            raise MemoryNotFoundError(f"Conversation not found: {conversation_id}")
        if conversation.memory_extraction_status == "completed":
            return MemoryExtractionResult(conversation_id=conversation_id)
        self._conversation_repository.start_extraction(conversation)
        messages = [
            MemoryExtractionMessage(id=message.id, role=message.role, content=message.content)
            for message in self._conversation_repository.list_messages(conversation_id)
            if message.role == MessageRole.USER.value
        ]
        if not messages:
            self._conversation_repository.finish_extraction(
                conversation, completed_at=self._clock(), error=None
            )
            return MemoryExtractionResult(conversation_id=conversation_id)
        existing: list[ExistingMemory] = []
        for memory in self._repository.list_memories(limit=50):
            person = self._repository.get_person(memory.person_id) if memory.person_id else None
            existing.append(
                ExistingMemory(
                    id=memory.id,
                    category=MemoryCategory(memory.category),
                    content=memory.content,
                    person_name=person.canonical_name if person else None,
                )
            )
        request = MemoryExtractionRequest(
            conversation_id=conversation_id,
            messages=messages,
            existing_memories=existing,
        )
        offered_memory_ids = {memory.id for memory in existing}
        try:
            candidates = await self._llm_provider.extract_memory_candidates(request)
        except LLMProviderError as exc:
            self._conversation_repository.finish_extraction(
                conversation, completed_at=self._clock(), error=str(exc)
            )
            return MemoryExtractionResult(
                conversation_id=conversation_id, error=str(exc), retryable=True
            )

        valid_source_ids = {message.id for message in messages}
        source_messages = {message.id: message for message in messages}
        result = MemoryExtractionResult(conversation_id=conversation_id)
        try:
            for candidate in candidates:
                if not set(candidate.source_message_ids).issubset(valid_source_ids):
                    result.skipped_count += 1
                    continue
                candidate_sources = [
                    source_messages[source_id].content for source_id in candidate.source_message_ids
                ]
                if all(_is_trivial_message(content) for content in candidate_sources):
                    result.skipped_count += 1
                    continue
                if (
                    candidate.updates_memory_id is not None
                    and candidate.updates_memory_id not in offered_memory_ids
                ):
                    raise MemoryValidationError("Memory update target was not offered")
                stored, created = self._store_candidate(candidate, conversation_id)
                schema = memory_to_schema(stored, self._repository)
                if created:
                    result.created.append(schema)
                else:
                    result.updated.append(schema)
            self._conversation_repository.finish_extraction(
                conversation, completed_at=self._clock(), error=None, commit=False
            )
            self._repository.commit()
            return result
        except (MemoryError, SQLAlchemyError, ValueError):
            self._repository.rollback()
            error = "Memory extraction could not be saved"
            self._conversation_repository.finish_extraction(
                conversation, completed_at=self._clock(), error=error
            )
            return MemoryExtractionResult(
                conversation_id=conversation_id, error=error, retryable=True
            )

    def _store_candidate(
        self,
        candidate: MemoryCandidate,
        conversation_id: str,
    ) -> tuple[Memory, bool]:
        return self._store(
            category=candidate.category,
            content=candidate.content,
            person_name=candidate.person_name,
            aliases=candidate.aliases,
            relationship_to_user=candidate.relationship_to_user,
            confidence=candidate.confidence,
            source_conversation_id=conversation_id,
            updates_memory_id=candidate.updates_memory_id,
        )

    def _store(
        self,
        *,
        category: MemoryCategory,
        content: str,
        person_name: str | None,
        aliases: list[str],
        relationship_to_user: str | None,
        confidence: float | None,
        source_conversation_id: str | None,
        updates_memory_id: str | None,
    ) -> tuple[Memory, bool]:
        now = self._clock()
        embedding = self._embed(content)
        person = None
        if person_name:
            person = self._repository.get_or_create_person(
                canonical_name=person_name,
                aliases=aliases,
                relationship_to_user=relationship_to_user,
                now=now,
                commit=source_conversation_id is None,
            )
        if updates_memory_id:
            existing = self._repository.get_memory(updates_memory_id)
            if existing is not None and existing.status == MemoryStatus.ACTIVE.value:
                return (
                    self._repository.update_memory(
                        existing,
                        content=content,
                        category=category,
                        person_id=person.id if person else None,
                        source_conversation_id=source_conversation_id,
                        confidence=confidence,
                        now=now,
                        embedding=embedding,
                        embedding_model=self._embedding_model(embedding),
                        commit=source_conversation_id is None,
                    ),
                    False,
                )
        duplicate = self._repository.find_duplicate(
            category=category,
            content=content,
            person_id=person.id if person else None,
        )
        if duplicate is not None:
            return (
                self._repository.update_memory(
                    duplicate,
                    content=None,
                    category=None,
                    person_id=None,
                    source_conversation_id=source_conversation_id,
                    confidence=confidence,
                    now=now,
                    embedding=embedding,
                    embedding_model=self._embedding_model(embedding),
                    commit=source_conversation_id is None,
                ),
                False,
            )
        return (
            self._repository.create_memory(
                category=category,
                content=content,
                person_id=person.id if person else None,
                source_conversation_id=source_conversation_id,
                confidence=confidence,
                now=now,
                embedding=embedding,
                embedding_model=self._embedding_model(embedding),
                commit=source_conversation_id is None,
            ),
            True,
        )

    def _embed(self, text: str) -> list[float] | None:
        if self._embedding_provider is None:
            return None
        try:
            embedding = normalize_embedding(self._embedding_provider.embed(text))
            if embedding is None or len(embedding) != self._embedding_provider.dimensions:
                return None
            return embedding
        except Exception:
            # Storing the memory remains more important than optional semantic
            # metadata when the embedding provider is unavailable.
            return None

    def _embedding_model(self, embedding: list[float] | None) -> str | None:
        if embedding is None or self._embedding_provider is None:
            return None
        return self._embedding_provider.model


def _is_trivial_message(content: str) -> bool:
    normalized = " ".join(content.casefold().strip().split()).rstrip(".!?。！？")
    return normalized in {
        "hello",
        "hi",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "你好",
        "嗨",
        "哈囉",
    }
