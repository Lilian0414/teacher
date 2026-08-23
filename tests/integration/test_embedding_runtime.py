import pytest

from companion.api.dependencies import get_embedding_provider
from companion.settings import Settings, get_settings


def test_runtime_factory_respects_embedding_enablement(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    get_embedding_provider.cache_clear()
    monkeypatch.setenv("COMPANION_EMBEDDINGS_ENABLED", "true")
    monkeypatch.setenv("COMPANION_EMBEDDING_DIMENSIONS", "2")
    provider = get_embedding_provider()
    assert provider is not None
    assert provider.dimensions == 2
    assert get_embedding_provider() is provider

    get_settings.cache_clear()
    get_embedding_provider.cache_clear()
    monkeypatch.setenv("COMPANION_EMBEDDINGS_ENABLED", "false")
    assert get_embedding_provider() is None
    get_settings.cache_clear()
    get_embedding_provider.cache_clear()


def test_settings_reject_invalid_embedding_dimensions() -> None:
    with pytest.raises(ValueError):
        Settings(embedding_dimensions=0)
