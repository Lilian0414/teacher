import sqlite3
from pathlib import Path

import pytest

from companion.settings import Settings
from companion.uat import (
    UATPreflightError,
    canonical_uat_database_path,
    canonical_uat_settings,
    preflight,
)


def test_canonical_uat_settings_ignore_stale_identity_and_database_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("COMPANION_USER_ID", "stale-user")
    monkeypatch.setenv("COMPANION_TIMEZONE", "Etc/UTC")
    monkeypatch.setenv("COMPANION_DATABASE_URL", "sqlite:////tmp/stale.sqlite3")

    settings = canonical_uat_settings()

    assert settings.user_id == "uat"
    assert settings.timezone == "Asia/Taipei"
    assert settings.sqlite_path == canonical_uat_database_path()


def test_uat_preflight_rejects_wrong_database_path() -> None:
    settings = Settings(database_url="sqlite:////tmp/not-final-uat.sqlite3")

    with pytest.raises(UATPreflightError, match="must resolve to"):
        preflight(settings)


def test_uat_preflight_rejects_database_behind_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings = canonical_uat_settings()
    assert settings.sqlite_path is not None
    settings.sqlite_path.parent.mkdir(parents=True)
    with sqlite3.connect(settings.sqlite_path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('old-revision')")

    with pytest.raises(UATPreflightError, match="current=old-revision"):
        preflight(settings)
