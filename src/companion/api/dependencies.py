from collections.abc import Generator

from sqlalchemy.orm import Session

from companion.availability import AvailabilityService
from companion.conversation import ConversationRepository, ConversationService
from companion.memory import MemoryContextBuilder, MemoryRepository, MemoryService
from companion.persistence.database import get_session
from companion.persistence.repositories import AvailabilityRepository
from companion.providers import FakeLLMProvider, GroqLLMProvider, LLMProvider
from companion.providers.errors import LLMConfigurationError
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
            status="configured" if configured else "unavailable",
        )
    if settings.llm_provider == "fake":
        return LLMStatus(
            provider="fake",
            model=None,
            configured=True,
            status="configured",
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
    if settings.llm_provider != "groq":
        raise LLMConfigurationError("Unsupported LLM_PROVIDER")
    return GroqLLMProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def get_conversation_service() -> Generator[ConversationService, None, None]:
    provider = get_llm_provider()
    for session in get_session():
        settings = get_settings()
        memory_repository = MemoryRepository(session)
        yield ConversationService(
            repository=ConversationRepository(session),
            llm_provider=provider,
            user_id=settings.user_id,
            context_limit=settings.conversation_context_limit,
            memory_context_builder=MemoryContextBuilder(
                memory_repository,
                limit=settings.memory_context_limit,
            ),
        )


def get_memory_service() -> Generator[MemoryService, None, None]:
    provider = get_llm_provider()
    for session in get_session():
        yield MemoryService(
            repository=MemoryRepository(session),
            conversation_repository=ConversationRepository(session),
            llm_provider=provider,
        )
