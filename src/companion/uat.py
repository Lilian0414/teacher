"""Guarded launcher for the canonical target-Mac final UAT profile."""

import json
import os
from pathlib import Path

from companion.settings import Settings, get_settings
from companion.uat_evidence import migration_snapshot

UAT_USER_ID = "uat"
UAT_TIMEZONE = "Asia/Taipei"


def canonical_database_path() -> Path:
    """Return the final-UAT path rooted in the current target user's home."""
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "ai-learning-companion"
        / "final-uat.sqlite3"
    )


class UATPreflightError(RuntimeError):
    """Raised when final-UAT verification would use an unsafe profile."""


def canonical_settings() -> Settings:
    """Resolve normal provider settings with canonical UAT identity/storage values."""
    return Settings(
        user_id=UAT_USER_ID,
        timezone=UAT_TIMEZONE,
        database_url=f"sqlite:///{canonical_database_path()}",
    )


def preflight(settings: Settings) -> dict[str, object]:
    """Validate and return the allow-listed UAT runtime profile."""
    actual_path = settings.sqlite_path
    expected_path = canonical_database_path().expanduser().resolve()
    if actual_path is None or actual_path.expanduser().resolve() != expected_path:
        displayed_path = actual_path or "non-SQLite URL"
        raise UATPreflightError(
            f"Refusing final UAT: database must be {expected_path}, got {displayed_path}"
        )
    if settings.user_id != UAT_USER_ID or settings.timezone != UAT_TIMEZONE:
        raise UATPreflightError(
            "Refusing final UAT: expected user_id=uat and timezone=Asia/Taipei"
        )

    migration = migration_snapshot(actual_path)
    if migration["current"] != migration["head"]:
        raise UATPreflightError(
            "Refusing final UAT: database migration is not at head "
            f"(current={migration['current']}, head={migration['head']})"
        )
    return {
        "database_path": str(expected_path),
        "user_id": settings.user_id,
        "timezone": settings.timezone,
        "core_url": settings.core_url,
        "alembic": migration,
    }


def main() -> None:
    """Preflight and launch Core+UI with only canonical UAT fields pinned."""
    settings = canonical_settings()
    profile = preflight(settings)
    print(json.dumps(profile, indent=2, sort_keys=True), flush=True)

    # Make the already-validated profile authoritative for both launcher processes.
    os.environ["COMPANION_USER_ID"] = settings.user_id
    os.environ["COMPANION_TIMEZONE"] = settings.timezone
    os.environ["COMPANION_DATABASE_URL"] = settings.database_url
    get_settings.cache_clear()
    from companion.cli import local

    local()
