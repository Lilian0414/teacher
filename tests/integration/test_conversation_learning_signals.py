from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from companion.conversation import ConversationRepository, ConversationService
from companion.learning import LearningContextBuilder, LearningRepository, LearningService
from companion.learning.schemas import (
    LearningKind,
    LearningSignalCandidate,
    LearningSignalReason,
    LearningSignalRequest,
)
from companion.persistence.database import Base, make_engine
from companion.providers.errors import LLMInvalidResponseError
from tests.support import RecordingLLMProvider


class BoundSignalProvider(RecordingLLMProvider):
    async def extract_learning_signal(
        self, request: LearningSignalRequest
    ) -> LearningSignalCandidate:
        self.learning_signal_requests.append(request)
        candidate = _candidate(
            conversation_id=request.conversation_id,
            user_id=request.user_message_id,
            assistant_id=request.assistant_message_id,
        )
        self.learning_signal = candidate
        return candidate


def _candidate(
    *,
    conversation_id: str = "offered-later",
    user_id: str = "offered-later",
    assistant_id: str = "offered-later",
) -> LearningSignalCandidate:
    return LearningSignalCandidate(
        source_conversation_id=conversation_id,
        source_user_message_id=user_id,
        source_assistant_message_id=assistant_id,
        kind=LearningKind.EXPRESSION,
        review_prompt="How can I say that today was exhausting?",
        accepted_answers=["I had an exhausting day."],
        reason=LearningSignalReason.USEFUL_EXPRESSION,
    )


@pytest.mark.asyncio
async def test_completed_turn_creates_due_item_with_durable_provenance_and_is_idempotent() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    with Session(engine) as session:
        provider = BoundSignalProvider()
        learning_repository = LearningRepository(session)
        learning = LearningService(repository=learning_repository, clock=lambda: now)
        service = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            learning_service=learning,
            learning_context_builder=LearningContextBuilder(learning_repository),
            clock=lambda: now,
        )
        conversation = service.create_conversation()

        result = await service.send_user_message(
            conversation_id=conversation.id, content="Today was completely exhausting."
        )

        assert result.error is None
        assert result.assistant_message is not None
        occurrence = learning_repository.occurrences()[0]
        request = provider.learning_signal_requests[0]
        assert occurrence.source_conversation_id == conversation.id
        assert occurrence.source_user_message_id == result.user_message.id
        assert occurrence.source_assistant_message_id == result.assistant_message.id
        assert occurrence.acceptance_reason == "useful_expression"
        assert learning.due_count() == 1
        context = LearningContextBuilder(learning_repository).build(now)
        assert context is not None
        assert "How can I say" in context

        assert provider.learning_signal is not None
        learning.capture_conversation_signal(request=request, candidate=provider.learning_signal)
        assert len(learning_repository.occurrences()) == 1
        assert learning.due_count() == 1
        item = learning_repository.due_items(user_id="default", now=now)[0]
        assert learning_repository.answers(item) == ["I had an exhausting day."]
        assert item.stage == 0
        assert item.next_review_at == now.isoformat()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, LLMInvalidResponseError("malformed")])
async def test_no_candidate_or_extraction_failure_preserves_successful_chat(
    failure: Exception | None,
) -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        provider = RecordingLLMProvider()
        provider.learning_signal_error = failure
        repository = LearningRepository(session)
        service = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            learning_service=LearningService(repository=repository),
        )
        conversation = service.create_conversation()
        result = await service.send_user_message(conversation_id=conversation.id, content="Hello!")

        assert result.error is None
        assert result.assistant_message is not None
        assert repository.due_count(user_id="default", now=datetime.max.replace(tzinfo=UTC)) == 0
        assert repository.occurrences() == []


@pytest.mark.asyncio
async def test_greeting_candidate_is_rejected_by_python_eligibility_gate() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        provider = BoundSignalProvider()
        repository = LearningRepository(session)
        service = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            learning_service=LearningService(repository=repository),
        )
        conversation = service.create_conversation()

        result = await service.send_user_message(conversation_id=conversation.id, content="Hello!")

        assert result.assistant_message is not None
        assert repository.occurrences() == []
        assert repository.due_count(user_id="default", now=datetime.max.replace(tzinfo=UTC)) == 0


@pytest.mark.asyncio
async def test_unoffered_source_identifier_is_rejected_without_mutation() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        provider = RecordingLLMProvider()
        provider.learning_signal = _candidate()
        repository = LearningRepository(session)
        service = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            learning_service=LearningService(repository=repository),
        )
        conversation = service.create_conversation()
        result = await service.send_user_message(
            conversation_id=conversation.id, content="Please correct this sentence."
        )

        assert result.assistant_message is not None
        assert repository.occurrences() == []
        assert repository.due_count(user_id="default", now=datetime.max.replace(tzinfo=UTC)) == 0
