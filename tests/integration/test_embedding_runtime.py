import pytest

from companion.api.dependencies import get_embedding_provider
from companion.providers.embeddings import OpenAIEmbeddingProvider
from companion.settings import Settings, get_settings


def test_runtime_factory_accepts_documented_unprefixed_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    get_embedding_provider.cache_clear()
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://embeddings.test/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "test-embedding-model")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "2")
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("EMBEDDING_BACKFILL_LIMIT", "4")

    provider = get_embedding_provider()

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider._base_url == "http://embeddings.test/v1"
    assert provider.model == "test-embedding-model"
    assert provider.dimensions == 2
    settings = get_settings()
    assert settings.embedding_api_key == "test-key"
    assert settings.embedding_timeout_seconds == 3.5
    assert settings.embedding_backfill_limit == 4
    assert get_embedding_provider() is provider
    get_settings.cache_clear()
    get_embedding_provider.cache_clear()


def test_settings_accept_prefixed_embedding_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    get_embedding_provider.cache_clear()
    monkeypatch.setenv("COMPANION_EMBEDDINGS_ENABLED", "true")
    monkeypatch.setenv("COMPANION_EMBEDDING_BASE_URL", "http://prefixed.test/v1")
    monkeypatch.setenv("COMPANION_EMBEDDING_API_KEY", "prefixed-key")
    monkeypatch.setenv("COMPANION_EMBEDDING_MODEL", "prefixed-model")
    monkeypatch.setenv("COMPANION_EMBEDDING_DIMENSIONS", "3")
    monkeypatch.setenv("COMPANION_EMBEDDING_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("COMPANION_EMBEDDING_BACKFILL_LIMIT", "5")

    settings = get_settings()

    assert settings.embeddings_enabled is True
    assert settings.embedding_base_url == "http://prefixed.test/v1"
    assert settings.embedding_api_key == "prefixed-key"
    assert settings.embedding_model == "prefixed-model"
    assert settings.embedding_dimensions == 3
    assert settings.embedding_timeout_seconds == 4.5
    assert settings.embedding_backfill_limit == 5
    get_settings.cache_clear()
    get_embedding_provider.cache_clear()


def test_settings_reject_invalid_embedding_dimensions() -> None:
    with pytest.raises(ValueError):
        Settings(embedding_dimensions=0)
