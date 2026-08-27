from datetime import UTC, datetime, timedelta

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
from companion.providers.errors import LLMInvalidResponseError, LLMTemporaryError
from companion.providers.schemas import ChatRequest, ChatResponse
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
        accepted_answers=["I am exhausted."],
        reason=LearningSignalReason.USEFUL_EXPRESSION,
    )


@pytest.mark.asyncio
async def test_completed_turn_delays_first_review_with_durable_provenance() -> None:
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
        assert learning.due_count() == 0
        context = LearningContextBuilder(learning_repository).build(now)
        assert context is None

        assert provider.learning_signal is not None
        learning.capture_conversation_signal(request=request, candidate=provider.learning_signal)
        assert len(learning_repository.occurrences()) == 1
        assert learning.due_count() == 0
        item = learning_repository.get_item(occurrence.learning_item_id, user_id="default")
        assert item is not None
        assert learning_repository.answers(item) == ["I am exhausted."]
        assert item.stage == 0
        assert item.next_review_at == (now + timedelta(days=1)).isoformat()
        assert learning_repository.due_count(
            user_id="default", now=now + timedelta(days=1) - timedelta(microseconds=1)
        ) == 0
        assert learning_repository.due_count(
            user_id="default", now=now + timedelta(days=1)
        ) == 1

        now += timedelta(days=1)
        review = learning.answer(item_id=item.id, answer="I'm exhausted.")
        assert review.correct is True
        assert review.stage == 1
        assert len(learning_repository.attempts_for(item.id)) == 1


@pytest.mark.asyncio
async def test_translated_say_turn_is_not_eligible_for_conversation_learning() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        provider = BoundSignalProvider()
        learning_repository = LearningRepository(session)
        service = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            learning_service=LearningService(repository=learning_repository),
        )
        conversation = service.create_conversation()

        result = await service.insert_translated_user_message(
            conversation_id=conversation.id,
            english_content="Today was completely exhausting.",
        )
        stored = service.get_conversation(conversation.id)

        assert result.error is None
        assert [message.role.value for message in stored.messages] == ["user", "assistant"]
        assert stored.messages[0].source == "say"
        assert provider.learning_signal_requests == []
        assert learning_repository.occurrences() == []
        assert learning_repository.due_count(
            user_id="default", now=datetime.max.replace(tzinfo=UTC)
        ) == 0


@pytest.mark.asyncio
async def test_translated_say_retry_remains_ineligible_without_duplicate_messages() -> None:
    class FailChatOnceProvider(BoundSignalProvider):
        async def chat(self, request: ChatRequest) -> ChatResponse:
            self.chat_requests.append(request)
            if len(self.chat_requests) == 1:
                raise LLMTemporaryError("Assistant is temporarily unavailable")
            return ChatResponse(content="Recovered assistant reply")

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        provider = FailChatOnceProvider()
        learning_repository = LearningRepository(session)
        service = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            learning_service=LearningService(repository=learning_repository),
        )
        conversation = service.create_conversation()

        partial = await service.insert_translated_user_message(
            conversation_id=conversation.id,
            english_content="Today was completely exhausting.",
        )
        retried = await service.retry_assistant_reply(
            conversation_id=conversation.id,
            user_message_id=partial.user_message.id,
        )
        repeated = await service.retry_assistant_reply(
            conversation_id=conversation.id,
            user_message_id=partial.user_message.id,
        )
        stored = service.get_conversation(conversation.id)

        assert partial.assistant_message is None
        assert partial.retryable is True
        assert retried.assistant_message is not None
        assert repeated.assistant_message == retried.assistant_message
        assert [message.role.value for message in stored.messages] == ["user", "assistant"]
        assert stored.messages[0].source == "say"
        assert provider.learning_signal_requests == []
        assert learning_repository.occurrences() == []
        assert learning_repository.due_count(
            user_id="default", now=datetime.max.replace(tzinfo=UTC)
        ) == 0


@pytest.mark.asyncio
async def test_ordinary_retry_reuses_original_pair_and_captures_learning_once() -> None:
    class FailChatOnceProvider(BoundSignalProvider):
        async def chat(self, request: ChatRequest) -> ChatResponse:
            self.chat_requests.append(request)
            if len(self.chat_requests) == 1:
                raise LLMTemporaryError("Assistant is temporarily unavailable")
            return ChatResponse(content="Recovered assistant reply")

    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        provider = FailChatOnceProvider()
        learning_repository = LearningRepository(session)
        service = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            learning_service=LearningService(repository=learning_repository),
        )
        conversation = service.create_conversation()

        partial = await service.send_user_message(
            conversation_id=conversation.id,
            content="Today was completely exhausting.",
        )
        retried = await service.retry_assistant_reply(
            conversation_id=conversation.id,
            user_message_id=partial.user_message.id,
        )
        repeated = await service.retry_assistant_reply(
            conversation_id=conversation.id,
            user_message_id=partial.user_message.id,
        )
        stored = service.get_conversation(conversation.id)

        assert partial.assistant_message is None
        assert retried.assistant_message is not None
        assert repeated.user_message.id == partial.user_message.id
        assert repeated.assistant_message == retried.assistant_message
        assert [message.id for message in stored.messages] == [
            partial.user_message.id,
            retried.assistant_message.id,
        ]
        occurrences = learning_repository.occurrences()
        assert len(occurrences) == 1
        assert occurrences[0].source_user_message_id == partial.user_message.id
        assert occurrences[0].source_assistant_message_id == retried.assistant_message.id
        assert len(provider.learning_signal_requests) == 1


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
@pytest.mark.parametrize("greeting", ["Hello!", "Hello there", "Hey, how's it going?"])
async def test_greeting_candidate_is_rejected_by_python_eligibility_gate(greeting: str) -> None:
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

        result = await service.send_user_message(conversation_id=conversation.id, content=greeting)

        assert result.assistant_message is not None
        assert repository.occurrences() == []
        assert repository.due_count(user_id="default", now=datetime.max.replace(tzinfo=UTC)) == 0


@pytest.mark.asyncio
async def test_substantive_turn_starting_with_greeting_remains_eligible() -> None:
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

        result = await service.send_user_message(
            conversation_id=conversation.id,
            content="Hello, I don't know how to say that I missed class",
        )

        assert result.assistant_message is not None
        assert len(repository.occurrences()) == 1
        assert repository.due_count(user_id="default", now=datetime.max.replace(tzinfo=UTC)) == 1


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("review_prompt", "answers"),
    [
        ('What is the correct spelling of "perents"?', [" parents ", "PARENTS!", "parents"]),
        ('What is the correct past tense of "go"?', ["went"]),
        ('Correct this sentence: "I goed home."', ["I went home."]),
    ],
)
async def test_standalone_signals_persist_normalized_answers_and_keep_identity(
    review_prompt: str, answers: list[str]
) -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        provider_candidate = _candidate()
        provider_candidate.review_prompt = review_prompt
        provider_candidate.accepted_answers = answers

        class StandaloneProvider(BoundSignalProvider):
            async def extract_learning_signal(
                self, request: LearningSignalRequest
            ) -> LearningSignalCandidate:
                self.learning_signal_requests.append(request)
                return provider_candidate.model_copy(
                    update={
                        "source_conversation_id": request.conversation_id,
                        "source_user_message_id": request.user_message_id,
                        "source_assistant_message_id": request.assistant_message_id,
                    }
                )

        repository = LearningRepository(session)
        service = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=StandaloneProvider(),
            learning_service=LearningService(repository=repository),
        )
        conversation = service.create_conversation()

        first = await service.send_user_message(
            conversation_id=conversation.id, content="Please help me practice this correction."
        )
        second = await service.send_user_message(
            conversation_id=conversation.id, content="Please help me practice it again."
        )

        assert first.assistant_message is not None and second.assistant_message is not None
        occurrences = repository.occurrences()
        assert len(occurrences) == 2
        assert occurrences[0].learning_item_id == occurrences[1].learning_item_id
        item = repository.get_item(occurrences[0].learning_item_id, user_id="default")
        assert item is not None
        expected = ["parents"] if "perents" in review_prompt else answers
        assert repository.answers(item) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "review_prompt",
    [
        "Correct the misspelled word in the user's sentence.",
        "Correct the sentence above.",
        "What does the phrase above mean?",
        "Fix this sentence.",
    ],
)
async def test_context_dependent_signal_creates_no_item_or_occurrence(review_prompt: str) -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        candidate = _candidate()
        candidate.review_prompt = review_prompt

        class ContextDependentProvider(BoundSignalProvider):
            async def extract_learning_signal(
                self, request: LearningSignalRequest
            ) -> LearningSignalCandidate:
                return candidate.model_copy(
                    update={
                        "source_conversation_id": request.conversation_id,
                        "source_user_message_id": request.user_message_id,
                        "source_assistant_message_id": request.assistant_message_id,
                    }
                )

        repository = LearningRepository(session)
        service = ConversationService(
            repository=ConversationRepository(session),
            llm_provider=ContextDependentProvider(),
            learning_service=LearningService(repository=repository),
        )
        conversation = service.create_conversation()

        await service.send_user_message(
            conversation_id=conversation.id, content="Please correct my English sentence."
        )

        assert repository.occurrences() == []
        assert repository.due_items(
            user_id="default", now=datetime.max.replace(tzinfo=UTC)
        ) == []
