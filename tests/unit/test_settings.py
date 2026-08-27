from pathlib import Path

import pytest
from pydantic import ValidationError

from companion.persistence.database import make_engine
from companion.settings import Settings


def test_example_environment_enables_documented_semantic_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "EMBEDDINGS_ENABLED",
        "COMPANION_EMBEDDINGS_ENABLED",
        "EMBEDDING_BASE_URL",
        "COMPANION_EMBEDDING_BASE_URL",
        "EMBEDDING_MODEL",
        "COMPANION_EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
        "COMPANION_EMBEDDING_DIMENSIONS",
        "EMBEDDING_TIMEOUT_SECONDS",
        "COMPANION_EMBEDDING_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    example_environment = Path(__file__).parents[2] / ".env.example"
    settings = Settings(_env_file=example_environment)  # type: ignore[call-arg]

    assert settings.embeddings_enabled is True
    assert settings.embedding_base_url == "http://127.0.0.1:11434/v1"
    assert settings.embedding_model == "nomic-embed-text"
    assert settings.embedding_dimensions == 768
    assert settings.embedding_timeout_seconds == 10


def test_default_groq_model_is_supported_replacement() -> None:
    assert Settings().groq_model == "openai/gpt-oss-20b"


def test_explicit_dotenv_opt_in_still_works(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("COMPANION_USER_ID=explicit-user\n", encoding="utf-8")

    assert Settings(_env_file=dotenv).user_id == "explicit-user"  # type: ignore[call-arg]


def test_pytest_ignores_hostile_repository_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(
        "COMPANION_USER_ID=hostile\n"
        "COMPANION_TIMEZONE=UTC\n"
        "COMPANION_DATABASE_URL=sqlite:////tmp/hostile.sqlite3\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.user_id == "default"
    assert settings.timezone == "Asia/Taipei"
    assert settings.sqlite_path != Path("/tmp/hostile.sqlite3")


def test_proactive_poll_interval_defaults_to_30_seconds() -> None:
    assert Settings(_env_file=None).proactive_poll_interval_seconds == 30  # type: ignore[call-arg]


def test_proactive_poll_interval_reads_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPANION_PROACTIVE_POLL_INTERVAL_SECONDS", "5")

    assert Settings(_env_file=None).proactive_poll_interval_seconds == 5  # type: ignore[call-arg]


def test_proactive_poll_interval_rejects_values_below_five() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, proactive_poll_interval_seconds=4)  # type: ignore[call-arg]


def test_default_database_is_absolute_and_cwd_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    first = Settings()
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    second = Settings()
    assert first.database_url == second.database_url
    assert first.sqlite_path is not None and first.sqlite_path.is_absolute()


def test_relative_sqlite_override_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        make_engine("sqlite:///./relative.sqlite3")
