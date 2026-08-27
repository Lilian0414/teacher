import pytest

from companion.api.dependencies import (
    _get_fail_once_provider,
    get_llm_provider,
    get_llm_status,
)
from companion.providers.fake import FailOnceFakeLLMProvider
from companion.settings import get_settings


def test_fake_fail_once_provider_selection_is_process_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake_fail_once")
    get_settings.cache_clear()
    _get_fail_once_provider.cache_clear()
    try:
        first = get_llm_provider()
        second = get_llm_provider()

        assert isinstance(first, FailOnceFakeLLMProvider)
        assert second is first
        status = get_llm_status()
        assert status.provider == "fake_fail_once"
        assert status.configured is True
        assert status.status == "usable"
    finally:
        get_settings.cache_clear()
        _get_fail_once_provider.cache_clear()
