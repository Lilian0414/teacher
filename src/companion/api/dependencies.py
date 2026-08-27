from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.orm import Session

from companion.availability import AvailabilityService
from companion.conversation.repository import ConversationRepository
from companion.conversation.service import ConversationService
from companion.learning.context import LearningContextBuilder
from companion.learning.repository import LearningRepository
from companion.learning.service import LearningService
from companion.memory.context import MemoryContextBuilder
from companion.memory.repository import MemoryRepository
from companion.memory.service import MemoryService
from companion.persistence.database import get_session
from companion.persistence.repositories import AvailabilityRepository
from companion.preferences import PreferencesRepository, PreferencesService
from companion.proactive import ProactiveRepository, ProactiveService
from companion.providers.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from companion.providers.errors import LLMConfigurationError
from companion.providers.fake import FailOnceFakeLLMProvider, FakeLLMProvider
from companion.providers.groq import GroqLLMProvider
from companion.providers.protocols import LLMProvider
from companion.schemas.availability import LLMStatus
from companion.settings import get_settings


def get_llm_status() -> LLMStatus:
    settings = get_settings()
    if settings.llm_provider == "groq":
        configured = bool(settings.groq_api_key)
        return LLMStatus(
            provider="groq",
            model=settings.groq_model,
            configured=configured,
            status="key_present_unverified" if configured else "missing_api_key",
        )
    if settings.llm_provider in {"fake", "fake_fail_once"}:
        return LLMStatus(
            provider=settings.llm_provider,
            model=None,
            configured=True,
            status="usable",
        )
    return LLMStatus(
        provider=settings.llm_provider,
        model=None,
        configured=False,
        status="unavailable",
    )


def get_availability_service() -> Generator[AvailabilityService, None, None]:
    for session in get_session():
        yield build_availability_service(session)


def build_availability_service(session: Session) -> AvailabilityService:
    settings = get_settings()
    return AvailabilityService(
        repository=AvailabilityRepository(session),
        user_id=settings.user_id,
    )


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if settings.llm_provider == "fake_fail_once":
        return _get_fail_once_provider()
    if settings.llm_provider != "groq":
        raise LLMConfigurationError("Unsupported LLM_PROVIDER")
    return GroqLLMProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )


@lru_cache(maxsize=1)
def _get_fail_once_provider() -> FailOnceFakeLLMProvider:
    # One process-scoped instance lets an HTTP retry succeed. Restarting Core resets it.
    return FailOnceFakeLLMProvider()


@lru_cache
def get_embedding_provider() -> EmbeddingProvider | None:
    settings = get_settings()
    if not settings.embeddings_enabled:
        return None
    return OpenAIEmbeddingProvider(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.embedding_timeout_seconds,
    )


def get_conversation_service() -> Generator[ConversationService, None, None]:
    provider = get_llm_provider()
    embedding_provider = get_embedding_provider()
    for session in get_session():
        settings = get_settings()
        memory_repository = MemoryRepository(session)
        learning_service = LearningService(
            repository=LearningRepository(session),
            user_id=settings.user_id,
        )
        proactive_service = ProactiveService(
            repository=ProactiveRepository(session),
            availability=build_availability_service(session),
            learning=learning_service,
            settings=settings,
            preferences=PreferencesService(PreferencesRepository(session), settings.user_id),
        )
        preferences_service = PreferencesService(PreferencesRepository(session), settings.user_id)
        yield ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            user_id=settings.user_id,
            context_limit=settings.conversation_context_limit,
            memory_context_builder=MemoryContextBuilder(
                memory_repository,
                limit=settings.memory_context_limit,
                embedding_provider=embedding_provider,
            ),
            learning_context_builder=LearningContextBuilder(
                LearningRepository(session),
                user_id=settings.user_id,
                limit=settings.learning_context_limit,
            ),
            learning_service=learning_service,
            practice_reconciler=proactive_service.reconcile_accepted_practices,
            correction_style=preferences_service.correction_style,
        )


def get_memory_service() -> Generator[MemoryService, None, None]:
    provider = get_llm_provider()
    embedding_provider = get_embedding_provider()
    for session in get_session():
        yield MemoryService(
            repository=MemoryRepository(session),
            conversation_repository=ConversationRepository(session),
            llm_provider=provider,
            embedding_provider=embedding_provider,
        )


def get_learning_service() -> Generator[LearningService, None, None]:
    for session in get_session():
        settings = get_settings()
        yield LearningService(
            repository=LearningRepository(session),
            user_id=settings.user_id,
        )


def get_proactive_service() -> Generator[ProactiveService, None, None]:
    for session in get_session():
        settings = get_settings()
        yield ProactiveService(
            repository=ProactiveRepository(session),
            availability=build_availability_service(session),
            learning=LearningService(
                repository=LearningRepository(session),
                user_id=settings.user_id,
            ),
            settings=settings,
            preferences=PreferencesService(PreferencesRepository(session), settings.user_id),
        )


def get_preferences_service() -> Generator[PreferencesService, None, None]:
    for session in get_session():
        settings = get_settings()
        yield PreferencesService(PreferencesRepository(session), settings.user_id)
