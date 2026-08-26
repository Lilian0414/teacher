import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from companion.conversation import ConversationRepository, ConversationService
from companion.memory import MemoryContextBuilder, MemoryRepository
from companion.memory.schemas import MemoryCategory
from companion.persistence.database import Base, make_engine
from companion.providers.schemas import ChatRequest
from companion.schemas.conversation import MessageRole
from tests.support import RecordingLLMProvider


class EventEmbeddingProvider:
    model = "semantic-test-v1"
    dimensions = 2

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        self.started.set()
        await self.release.wait()
        return self.vectors[text]

    async def embed_many(self, texts: Sequence[str]) -> list[Sequence[float]]:
        return [self.vectors[text] for text in texts]


@pytest.mark.asyncio
async def test_zero_overlap_semantic_memory_reaches_chat_context_without_blocking_loop() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = Session(engine)
    memories = MemoryRepository(session)
    conversations = ConversationRepository(session)
    llm = RecordingLLMProvider()
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    stored_text = "My favorite meal is salmon."
    query = "What food do I like best?"
    memories.create_memory(
        category=MemoryCategory.PERSONAL,
        content=stored_text,
        person_id=None,
        source_conversation_id=None,
        confidence=1.0,
        now=now,
        embedding=[1.0, 0.0],
        embedding_model="semantic-test-v1",
    )
    memories.create_memory(
        category=MemoryCategory.OTHER,
        content="A distant galaxy contains many stars.",
        person_id=None,
        source_conversation_id=None,
        confidence=1.0,
        now=now,
        embedding=[0.0, 1.0],
        embedding_model="semantic-test-v1",
    )
    deleted = memories.create_memory(
        category=MemoryCategory.PERSONAL,
        content="The learner loves tuna.",
        person_id=None,
        source_conversation_id=None,
        confidence=1.0,
        now=now,
        embedding=[1.0, 0.0],
        embedding_model="semantic-test-v1",
    )
    memories.soft_delete(deleted, now=now)
    embeddings = EventEmbeddingProvider({query: [1.0, 0.0]})
    service = ConversationService(
        repository=conversations,
        llm_provider=llm,
        clock=lambda: now,
        memory_context_builder=MemoryContextBuilder(memories, embedding_provider=embeddings),
    )
    conversation = service.create_conversation()

    send_task = asyncio.create_task(
        service.send_user_message(conversation_id=conversation.id, content=query)
    )
    await embeddings.started.wait()
    unrelated_progress = False

    async def unrelated_work() -> None:
        nonlocal unrelated_progress
        await asyncio.sleep(0)
        unrelated_progress = True

    await unrelated_work()
    assert unrelated_progress is True
    assert not send_task.done()
    embeddings.release.set()
    result = await send_task

    assert result.error is None
    assert embeddings.calls == [query]
    request: ChatRequest = llm.chat_requests[-1]
    system_context = next(
        message.content for message in request.messages if message.role == "system"
    )
    assert stored_text in system_context
    assert "distant galaxy" not in system_context
    assert "loves tuna" not in system_context
    assert any(message.role == MessageRole.USER.value for message in request.messages)
