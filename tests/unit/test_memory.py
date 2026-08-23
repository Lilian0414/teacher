from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from companion.conversation import ConversationRepository
from companion.memory import MemoryContextBuilder, MemoryRepository, MemoryService
from companion.memory.schemas import (
    MemoryAnalysis,
    MemoryCandidate,
    MemoryCategory,
    MemoryStatus,
)
from companion.persistence.database import Base, make_engine
from companion.providers.embeddings import EmbeddingProvider
from companion.schemas.conversation import MessageRole
from tests.support import RecordingLLMProvider


class DeterministicEmbeddingProvider:
    def __init__(
        self,
        vectors: dict[str, list[float]],
        *,
        fail_for: set[str] | None = None,
    ) -> None:
        self._vectors = vectors
        self._fail_for = fail_for or set()

    @property
    def model(self) -> str:
        return "deterministic-v1"

    @property
    def dimensions(self) -> int:
        return 2

    def embed(self, text: str) -> list[float]:
        if text in self._fail_for:
            raise RuntimeError("embedding provider unavailable")
        return list(self._vectors.get(text, [0.0, 0.0]))


def make_memory_services(
    embedding_provider: EmbeddingProvider | None = None,
) -> tuple[
    Session,
    ConversationRepository,
    MemoryRepository,
    MemoryService,
    RecordingLLMProvider,
]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    conversations = ConversationRepository(session)
    memories = MemoryRepository(session)
    provider = RecordingLLMProvider()
    service = MemoryService(
        repository=memories,
        conversation_repository=conversations,
        llm_provider=provider,
        embedding_provider=embedding_provider,
        clock=lambda: datetime(2026, 7, 19, 12, tzinfo=UTC),
    )
    return session, conversations, memories, service, provider


@pytest.mark.asyncio
async def test_remember_exact_duplicate_merges_instead_of_creating_again() -> None:
    _, _, repository, service, provider = make_memory_services()
    provider.memory_analysis = MemoryAnalysis(
        category=MemoryCategory.PEOPLE,
        person_name="Andy",
        relationship_to_user="university classmate",
        confidence=1.0,
    )

    first = await service.remember("Andy is my university classmate.")
    second = await service.remember("  Andy is my university classmate.  ")

    assert first.id == second.id
    assert len(repository.list_memories()) == 1
    assert second.person is not None
    assert second.person.canonical_name == "Andy"


@pytest.mark.asyncio
async def test_extraction_saves_explicit_person_event_and_excludes_assistant() -> None:
    _, conversations, repository, service, provider = make_memory_services()
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    conversation = conversations.create_conversation(user_id="default", started_at=now)
    user_message = conversations.add_message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="Anny and Larry argued yesterday.",
        language="en",
        source="terminal",
        created_at=now,
    )
    assistant_message = conversations.add_message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="Maybe they are ending their friendship.",
        language="en",
        source="terminal",
        created_at=now + timedelta(seconds=1),
    )
    provider.memory_candidates = [
        MemoryCandidate(
            category=MemoryCategory.RELATIONSHIPS,
            content="Anny and Larry argued yesterday.",
            person_name="Anny",
            confidence=0.95,
            source_message_ids=[user_message.id],
        ),
        MemoryCandidate(
            category=MemoryCategory.RELATIONSHIPS,
            content="Anny and Larry may end their friendship.",
            person_name="Anny",
            confidence=0.3,
            source_message_ids=[assistant_message.id],
        ),
    ]

    result = await service.extract_conversation(conversation.id)

    assert [memory.content for memory in result.created] == [
        "Anny and Larry argued yesterday."
    ]
    assert result.skipped_count == 1
    assert len(repository.list_memories()) == 1
    request = provider.memory_extraction_requests[0]
    assert [message.role for message in request.messages] == ["user"]
    assert "ending their friendship" not in request.model_dump_json()


@pytest.mark.asyncio
async def test_greeting_candidate_is_rejected_by_policy() -> None:
    _, conversations, repository, service, provider = make_memory_services()
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    conversation = conversations.create_conversation(user_id="default", started_at=now)
    greeting = conversations.add_message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="Hello!",
        language="en",
        source="terminal",
        created_at=now,
    )
    provider.memory_candidates = [
        MemoryCandidate(
            category=MemoryCategory.OTHER,
            content="The user said hello.",
            confidence=1.0,
            source_message_ids=[greeting.id],
        )
    ]

    result = await service.extract_conversation(conversation.id)

    assert result.created == []
    assert result.skipped_count == 1
    assert repository.list_memories() == []


@pytest.mark.asyncio
async def test_candidate_update_changes_existing_memory_without_duplicate() -> None:
    _, conversations, repository, service, provider = make_memory_services()
    provider.memory_analysis = MemoryAnalysis(
        category=MemoryCategory.SCHOOL_WORK,
        person_name="Andy",
        confidence=1.0,
    )
    existing = await service.remember("Andy works at Company A.")
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    conversation = conversations.create_conversation(user_id="default", started_at=now)
    message = conversations.add_message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="Andy changed jobs and now works at Company B.",
        language="en",
        source="terminal",
        created_at=now,
    )
    provider.memory_candidates = [
        MemoryCandidate(
            category=MemoryCategory.SCHOOL_WORK,
            content="Andy now works at Company B.",
            person_name="Andy",
            confidence=0.98,
            source_message_ids=[message.id],
            updates_memory_id=existing.id,
        )
    ]

    result = await service.extract_conversation(conversation.id)

    assert result.created == []
    assert [memory.id for memory in result.updated] == [existing.id]
    assert repository.list_memories()[0].content == "Andy now works at Company B."
    assert len(repository.list_memories()) == 1


def test_memory_context_selects_only_relevant_memories_and_limits_to_five() -> None:
    _, _, repository, _, _ = make_memory_services()
    now = datetime(2026, 7, 19, 12, tzinfo=UTC)
    andy = repository.get_or_create_person(
        canonical_name="Andy",
        aliases=[],
        relationship_to_user="friend",
        now=now,
    )
    for index in range(7):
        repository.create_memory(
            category=MemoryCategory.PEOPLE,
            content=f"Andy shared event {index}.",
            person_id=andy.id,
            source_conversation_id=None,
            confidence=0.9,
            now=now + timedelta(seconds=index),
        )
    repository.create_memory(
        category=MemoryCategory.HEALTH_FITNESS,
        content="The user runs every Sunday.",
        person_id=None,
        source_conversation_id=None,
        confidence=1.0,
        now=now,
    )
    builder = MemoryContextBuilder(repository, limit=5)

    selected = builder.select("How has Andy been lately?")

    assert len(selected) == 5
    assert all("Andy" in memory.content for memory in selected)
    assert all(memory.status == MemoryStatus.ACTIVE for memory in selected)


@pytest.mark.asyncio
async def test_hybrid_retrieval_recalls_semantic_paraphrase_without_token_overlap() -> None:
    memory_text = "The learner struggles with remembering new vocabulary."
    query = "I keep forgetting new words."
    irrelevant = "Weekend hiking feels relaxing."
    embedding_provider = DeterministicEmbeddingProvider(
        {
            memory_text: [1.0, 0.0],
            query: [1.0, 0.0],
            irrelevant: [0.0, 1.0],
        }
    )
    _, _, repository, service, _ = make_memory_services(embedding_provider)
    await service.remember(memory_text)
    await service.remember(irrelevant)

    selected = MemoryContextBuilder(
        repository,
        embedding_provider=embedding_provider,
    ).select(query)

    assert [memory.content for memory in selected] == [memory_text]


@pytest.mark.asyncio
async def test_deleted_semantic_memory_is_never_recalled() -> None:
    memory_text = "The learner struggles with remembering new vocabulary."
    query = "I keep forgetting new words."
    embedding_provider = DeterministicEmbeddingProvider(
        {memory_text: [1.0, 0.0], query: [1.0, 0.0]}
    )
    _, _, repository, service, _ = make_memory_services(embedding_provider)
    remembered = await service.remember(memory_text)
    service.forget(remembered.id)

    selected = MemoryContextBuilder(
        repository,
        embedding_provider=embedding_provider,
    ).select(query)

    assert selected == []


@pytest.mark.asyncio
async def test_query_embedding_failure_falls_back_to_lexical_retrieval() -> None:
    memory_text = "Andy practices chess every Friday."
    query = "What does Andy practice on Friday?"
    embedding_provider = DeterministicEmbeddingProvider(
        {memory_text: [1.0, 0.0]},
        fail_for={query},
    )
    _, _, repository, service, provider = make_memory_services(embedding_provider)
    provider.memory_analysis = MemoryAnalysis(
        category=MemoryCategory.PEOPLE,
        person_name="Andy",
        confidence=1.0,
    )
    await service.remember(memory_text)

    selected = MemoryContextBuilder(
        repository,
        embedding_provider=embedding_provider,
    ).select(query)

    assert [memory.content for memory in selected] == [memory_text]


@pytest.mark.asyncio
async def test_embedding_is_persisted_and_decoded_without_provider_calls() -> None:
    memory_text = "The learner prefers short practice sessions."
    embedding_provider = DeterministicEmbeddingProvider({memory_text: [0.25, 0.75]})
    session, _, repository, service, _ = make_memory_services(embedding_provider)
    await service.remember(memory_text)

    memory_id = repository.list_memories()[0].id
    session.expire_all()
    reloaded = repository.get_memory(memory_id)

    assert reloaded is not None
    assert repository.decode_embedding(reloaded) == [0.25, 0.75]


@pytest.mark.asyncio
async def test_write_embedding_failure_still_saves_memory_for_lexical_recall() -> None:
    memory_text = "The learner reviews vocabulary at breakfast."
    embedding_provider = DeterministicEmbeddingProvider({}, fail_for={memory_text})
    _, _, repository, service, _ = make_memory_services(embedding_provider)

    remembered = await service.remember(memory_text)

    stored = repository.get_memory(remembered.id)
    assert stored is not None
    assert repository.decode_embedding(stored) is None
    assert [item.id for item in MemoryContextBuilder(repository).select("vocabulary")] == [
        remembered.id
    ]
