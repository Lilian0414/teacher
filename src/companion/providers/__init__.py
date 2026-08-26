"""Provider interfaces and compatibility exports.

Concrete implementations are loaded lazily so importing a provider schema does
not pull the application service graph into the interpreter.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from companion.providers.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
    from companion.providers.fake import FakeLLMProvider
    from companion.providers.groq import GroqLLMProvider
    from companion.providers.protocols import LLMProvider

__all__ = [
    "EmbeddingProvider",
    "FakeLLMProvider",
    "GroqLLMProvider",
    "LLMProvider",
    "OpenAIEmbeddingProvider",
]


def __getattr__(name: str) -> Any:
    if name == "LLMProvider":
        from companion.providers.protocols import LLMProvider

        return LLMProvider
    if name in {"EmbeddingProvider", "OpenAIEmbeddingProvider"}:
        from companion.providers import embeddings

        return getattr(embeddings, name)
    if name == "FakeLLMProvider":
        from companion.providers.fake import FakeLLMProvider

        return FakeLLMProvider
    if name == "GroqLLMProvider":
        from companion.providers.groq import GroqLLMProvider

        return GroqLLMProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
