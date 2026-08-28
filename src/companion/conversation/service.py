from collections.abc import Callable
from dataclasses import dataclass

from companion.clock import Clock, system_clock
from companion.conversation.repository import ConversationRepository
from companion.input_policy import BLOCKED_INPUT_SOURCE, ENGLISH_INPUT_REDIRECT, is_materially_han
from companion.learning.context import LearningContextBuilder
from companion.learning.schemas import LearningSignalExtraction, LearningSignalRequest
from companion.learning.service import LearningService
from companion.memory.context import MemoryContextBuilder
from companion.persistence.models import Conversation, Message
from companion.persistence.repositories import decode_dt
from companion.providers.errors import LLMProviderError
from companion.providers.protocols import LLMProvider
from companion.providers.schemas import ChatMessage, ChatRequest
from companion.schemas.conversation import (
    ConversationSchema,
    MemoryExtractionStatus,
    MessageRole,
    MessageSchema,
)

ORDINARY_CHAT_SOURCE = "terminal"
TRANSLATED_SAY_SOURCE = "say"


@dataclass(frozen=True)
class SendMessageResult:
    user_message: MessageSchema
    assistant_message: MessageSchema | None
    error: str | None
    retryable: bool


class ConversationNotFoundError(Exception):
    pass


class ConversationEndedError(Exception):
    pass


class MessageNotFoundError(Exception):
    pass


class AssistantRetryConflictError(Exception):
    pass


class ConversationService:
    def __init__(
        self,
        *,
        repository: ConversationRepository,
        llm_provider: LLMProvider,
        clock: Clock = system_clock,
        user_id: str = "default",
        context_limit: int = 20,
        memory_context_builder: MemoryContextBuilder | None = None,
        learning_context_builder: LearningContextBuilder | None = None,
        learning_service: LearningService | None = None,
        practice_reconciler: Callable[[], object] | None = None,
        correction_style: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._llm_provider = llm_provider
        self._clock = clock
        self._user_id = user_id
        self._context_limit = context_limit
        self._memory_context_builder = memory_context_builder
        self._learning_context_builder = learning_context_builder
        self._learning_service = learning_service
        self._practice_reconciler = practice_reconciler
        self._correction_style = correction_style or (lambda: "normal")

    def create_conversation(self) -> ConversationSchema:
        conversation = self._repository.create_conversation(
            user_id=self._user_id,
            started_at=self._clock(),
        )
        return self._conversation_schema(conversation)

    def get_conversation(self, conversation_id: str) -> ConversationSchema:
        conversation = self._require_conversation(conversation_id)
        messages = self._repository.list_messages(conversation_id)
        return self._conversation_schema(conversation, messages)

    def end_conversation(self, conversation_id: str) -> ConversationSchema:
        conversation = self._repository.end_conversation(
            conversation_id=conversation_id,
            ended_at=self._clock(),
        )
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        messages = self._repository.list_messages(conversation_id)
        return self._conversation_schema(conversation, messages)

    def recover_interrupted_conversations(self) -> list[ConversationSchema]:
        if self._practice_reconciler is not None:
            self._practice_reconciler()
        recovered: list[ConversationSchema] = []
        for conversation in self._repository.list_recoverable(user_id=self._user_id):
            if conversation.ended_at is None:
                ended = self._repository.end_conversation(
                    conversation_id=conversation.id, ended_at=self._clock()
                )
                assert ended is not None
                conversation = ended
            recovered.append(self._conversation_schema(conversation))
        return recovered

    async def send_user_message(self, *, conversation_id: str, content: str) -> SendMessageResult:
        conversation = self._require_conversation(conversation_id)
        if conversation.ended_at is not None:
            raise ConversationEndedError(conversation_id)
        user_message = self._repository.add_message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=content,
            language="en",
            source=BLOCKED_INPUT_SOURCE if is_materially_han(content) else ORDINARY_CHAT_SOURCE,
            created_at=self._clock(),
        )
        if user_message.source == BLOCKED_INPUT_SOURCE:
            assistant_message = self._repository.add_message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=ENGLISH_INPUT_REDIRECT,
                language="en",
                source=BLOCKED_INPUT_SOURCE,
                created_at=self._clock(),
            )
            return SendMessageResult(
                user_message=self._message_schema(user_message),
                assistant_message=self._message_schema(assistant_message),
                error=None,
                retryable=False,
            )
        return await self._reply_to_user_message(user_message)

    async def retry_assistant_reply(
        self, *, conversation_id: str, user_message_id: str
    ) -> SendMessageResult:
        conversation = self._require_conversation(conversation_id)
        if conversation.ended_at is not None:
            raise ConversationEndedError(conversation_id)
        target = self._repository.get_message(user_message_id)
        if target is None or target.conversation_id != conversation_id:
            raise MessageNotFoundError(user_message_id)
        if target.role != MessageRole.USER.value:
            raise AssistantRetryConflictError("Retry target must be a user message")

        messages = self._repository.list_messages(conversation_id)
        target_index = next(
            (index for index, message in enumerate(messages) if message.id == target.id), None
        )
        if target_index is None:
            raise MessageNotFoundError(user_message_id)
        later = messages[target_index + 1 :]
        if not later:
            return await self._reply_to_user_message(target)
        if len(later) == 1 and later[0].role == MessageRole.ASSISTANT.value:
            return SendMessageResult(
                user_message=self._message_schema(target),
                assistant_message=self._message_schema(later[0]),
                error=None,
                retryable=False,
            )
        raise AssistantRetryConflictError("Retry target is no longer the conversation tail")

    async def _reply_to_user_message(self, user_message: Message) -> SendMessageResult:
        try:
            assistant_content = await self._generate_assistant_reply(
                user_message.conversation_id,
                current_message=user_message.content,
            )
        except LLMProviderError as exc:
            return SendMessageResult(
                user_message=self._message_schema(user_message),
                assistant_message=None,
                error=str(exc),
                retryable=exc.retryable,
            )

        assistant_message = self._repository.add_message(
            conversation_id=user_message.conversation_id,
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            language="en",
            source="terminal",
            created_at=self._clock(),
        )
        if self._learning_service is not None and user_message.source == ORDINARY_CHAT_SOURCE:
            request = LearningSignalRequest(
                conversation_id=user_message.conversation_id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                user_content=user_message.content,
                assistant_content=assistant_message.content,
            )
            try:
                result = await self._llm_provider.extract_learning_signal(request)
                if isinstance(result, LearningSignalExtraction):
                    self._learning_service.capture_conversation_signal(
                        request=request,
                        candidate=result.candidate,
                        observation=result.observation,
                    )
                elif result is not None and not isinstance(result, LearningSignalExtraction):
                    # Local/test provider compatibility; production extraction is evidence-first.
                    self._learning_service.capture_conversation_signal(
                        request=request, candidate=result
                    )
            except Exception:
                # Learning extraction is best-effort post-processing; chat is already durable.
                pass
        return SendMessageResult(
            user_message=self._message_schema(user_message),
            assistant_message=self._message_schema(assistant_message),
            error=None,
            retryable=False,
        )

    async def insert_translated_user_message(
        self,
        *,
        conversation_id: str,
        english_content: str,
    ) -> SendMessageResult:
        conversation = self._require_conversation(conversation_id)
        if conversation.ended_at is not None:
            raise ConversationEndedError(conversation_id)
        user_message = self._repository.add_message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=english_content,
            language="en",
            source=TRANSLATED_SAY_SOURCE,
            created_at=self._clock(),
        )
        return await self._reply_to_user_message(user_message)

    async def _generate_assistant_reply(
        self,
        conversation_id: str,
        *,
        current_message: str,
    ) -> str:
        recent = self._repository.recent_messages(
            conversation_id=conversation_id,
            limit=self._context_limit,
        )
        messages = [
            ChatMessage(role=message.role, content=message.content)
            for message in recent
            if message.role in {MessageRole.USER.value, MessageRole.ASSISTANT.value}
            and message.source != BLOCKED_INPUT_SOURCE
        ]
        contexts: list[str] = []
        if self._memory_context_builder is not None:
            memory_context = await self._memory_context_builder.build(current_message)
            if memory_context:
                contexts.append(memory_context)
        if self._learning_context_builder is not None:
            learning_context = self._learning_context_builder.build(self._clock())
            if learning_context:
                contexts.append(learning_context)
        if contexts:
            messages.insert(0, ChatMessage(role="system", content="\n\n".join(contexts)))
        response = await self._llm_provider.chat(
            ChatRequest(messages=messages, correction_style=self._correction_style())
        )
        return response.content

    def _require_conversation(self, conversation_id: str) -> Conversation:
        conversation = self._repository.get_conversation(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return conversation

    def _conversation_schema(
        self,
        conversation: Conversation,
        messages: list[Message] | None = None,
    ) -> ConversationSchema:
        return ConversationSchema(
            id=conversation.id,
            user_id=conversation.user_id,
            mode=conversation.mode,
            private_mode=conversation.private_mode,
            started_at=decode_dt(conversation.started_at),
            ended_at=decode_dt(conversation.ended_at) if conversation.ended_at else None,
            memory_extraction_status=MemoryExtractionStatus(
                conversation.memory_extraction_status
            ),
            memory_extraction_attempts=conversation.memory_extraction_attempts,
            memory_extraction_error=conversation.memory_extraction_error,
            memory_extracted_at=(
                decode_dt(conversation.memory_extracted_at)
                if conversation.memory_extracted_at
                else None
            ),
            messages=[self._message_schema(message) for message in messages or []],
        )

    @staticmethod
    def _message_schema(message: Message) -> MessageSchema:
        return MessageSchema(
            id=message.id,
            conversation_id=message.conversation_id,
            role=MessageRole(message.role),
            content=message.content,
            language=message.language,
            source=message.source,
            created_at=decode_dt(message.created_at),
        )
