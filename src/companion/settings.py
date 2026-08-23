from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_database_url() -> str:
    """Return a database URL that never depends on the process working directory."""
    data_dir = Path.home() / "Library" / "Application Support" / "ai-learning-companion"
    return f"sqlite:///{data_dir / 'companion.sqlite3'}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="COMPANION_",
        extra="ignore",
    )

    env: str = "development"
    app_name: str = "AI Learning Companion Core"
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = Field(default_factory=default_database_url)
    timezone: str = "Asia/Taipei"
    user_id: str = "default"
    schema_version: int = Field(default=1, ge=1)
    busy_max_duration_hours: int = Field(default=24, ge=1)
    version: str = "0.1.0"
    llm_provider: str = Field(
        default="groq",
        validation_alias=AliasChoices("LLM_PROVIDER", "COMPANION_LLM_PROVIDER"),
    )
    groq_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GROQ_API_KEY", "COMPANION_GROQ_API_KEY"),
    )
    groq_model: str = Field(
        default="llama-3.1-8b-instant",
        validation_alias=AliasChoices("GROQ_MODEL", "COMPANION_GROQ_MODEL"),
    )
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        validation_alias=AliasChoices("GROQ_BASE_URL", "COMPANION_GROQ_BASE_URL"),
    )
    llm_timeout_seconds: float = Field(
        default=30,
        gt=0,
        validation_alias=AliasChoices("LLM_TIMEOUT_SECONDS", "COMPANION_LLM_TIMEOUT_SECONDS"),
    )
    conversation_context_limit: int = Field(
        default=20,
        ge=1,
        validation_alias=AliasChoices(
            "CONVERSATION_CONTEXT_LIMIT",
            "COMPANION_CONVERSATION_CONTEXT_LIMIT",
        ),
    )
    memory_context_limit: int = Field(
        default=5,
        ge=1,
        le=5,
        validation_alias=AliasChoices(
            "MEMORY_CONTEXT_LIMIT",
            "COMPANION_MEMORY_CONTEXT_LIMIT",
        ),
    )
    embeddings_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("EMBEDDINGS_ENABLED", "COMPANION_EMBEDDINGS_ENABLED"),
    )
    embedding_base_url: str = Field(
        default="http://127.0.0.1:11434/v1",
        validation_alias=AliasChoices("EMBEDDING_BASE_URL", "COMPANION_EMBEDDING_BASE_URL"),
    )
    embedding_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("EMBEDDING_API_KEY", "COMPANION_EMBEDDING_API_KEY"),
    )
    embedding_model: str = Field(
        default="nomic-embed-text",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "COMPANION_EMBEDDING_MODEL"),
    )
    embedding_dimensions: int = Field(
        default=768,
        ge=1,
        validation_alias=AliasChoices("EMBEDDING_DIMENSIONS", "COMPANION_EMBEDDING_DIMENSIONS"),
    )
    embedding_timeout_seconds: float = Field(
        default=10,
        gt=0,
        validation_alias=AliasChoices(
            "EMBEDDING_TIMEOUT_SECONDS",
            "COMPANION_EMBEDDING_TIMEOUT_SECONDS",
        ),
    )
    embedding_backfill_limit: int = Field(
        default=10,
        ge=0,
        le=100,
        validation_alias=AliasChoices(
            "EMBEDDING_BACKFILL_LIMIT",
            "COMPANION_EMBEDDING_BACKFILL_LIMIT",
        ),
    )
    learning_context_limit: int = Field(
        default=3,
        ge=1,
        le=5,
        validation_alias=AliasChoices(
            "LEARNING_CONTEXT_LIMIT",
            "COMPANION_LEARNING_CONTEXT_LIMIT",
        ),
    )
    proactive_poll_interval_seconds: int = Field(default=30, ge=5)
    proactive_review_idle_seconds: int = Field(default=600, ge=0)
    proactive_conversation_idle_seconds: int = Field(default=1800, ge=0)
    proactive_snooze_minutes: int = Field(default=30, ge=1)
    proactive_accept_cooldown_minutes: int = Field(default=60, ge=1)
    proactive_daily_limit: int = Field(default=3, ge=1, le=20)

    @property
    def sqlite_path(self) -> Path | None:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        return Path(self.database_url.removeprefix(prefix))

    @property
    def core_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
