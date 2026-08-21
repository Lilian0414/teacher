from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    database_url: str = "sqlite:///./data/companion.sqlite3"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
