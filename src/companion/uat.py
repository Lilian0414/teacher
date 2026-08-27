"""Guarded launcher for the canonical final target-Mac UAT profile."""

import json
import os
from pathlib import Path

from companion.settings import Settings, get_settings
from companion.uat_evidence import _alembic_head, _database_revision, configuration_snapshot

UAT_USER_ID = "uat"
UAT_TIMEZONE = "Asia/Taipei"


class UATPreflightError(RuntimeError):
    """Raised when final-UAT verification would use an unsafe runtime profile."""


def canonical_uat_database_path() -> Path:
    """Return the absolute, working-directory-independent final-UAT database path."""
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "ai-learning-companion"
        / "final-uat.sqlite3"
    )


def canonical_uat_settings() -> Settings:
    """Resolve normal provider settings while pinning final-UAT identity and storage."""
    database_url = f"sqlite:///{canonical_uat_database_path()}"
    return Settings(database_url=database_url, user_id=UAT_USER_ID, timezone=UAT_TIMEZONE)


def preflight(settings: Settings) -> None:
    """Reject a non-canonical database or a database not migrated to Alembic head."""
    expected = canonical_uat_database_path()
    actual = settings.sqlite_path
    if actual is None or actual.expanduser().resolve() != expected.resolve():
        resolved = actual or settings.database_url
        raise UATPreflightError(
            f"Final UAT database must resolve to {expected}; resolved {resolved}"
        )

    current = _database_revision(actual)
    head = _alembic_head()
    if current != head:
        raise UATPreflightError(
            f"Final UAT database migration is not at head: current={current}, head={head}. "
            "Run `alembic upgrade head` explicitly; the UAT launcher never resets the database."
        )


def main() -> None:
    """Validate and launch Core plus UI with the canonical final-UAT profile."""
    settings = canonical_uat_settings()
    preflight(settings)
    print(json.dumps(configuration_snapshot(settings), indent=2, sort_keys=True), flush=True)

    # Make the already-validated profile authoritative for the normal launcher's child Core.
    os.environ["COMPANION_DATABASE_URL"] = settings.database_url
    os.environ["COMPANION_USER_ID"] = settings.user_id
    os.environ["COMPANION_TIMEZONE"] = settings.timezone
    get_settings.cache_clear()

    from companion.cli import local

    local()


if __name__ == "__main__":
    main()
