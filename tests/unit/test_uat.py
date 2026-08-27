from pathlib import Path

import pytest

from companion.settings import Settings
from companion.uat import UATPreflightError, canonical_settings, preflight


def test_canonical_settings_ignore_stale_uat_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("COMPANION_USER_ID", "wrong")
    monkeypatch.setenv("COMPANION_TIMEZONE", "UTC")
    monkeypatch.setenv("COMPANION_DATABASE_URL", "sqlite:////tmp/stale.sqlite3")

    settings = canonical_settings()

    assert settings.user_id == "uat"
    assert settings.timezone == "Asia/Taipei"
    assert settings.sqlite_path == (
        tmp_path
        / "Library"
        / "Application Support"
        / "ai-learning-companion"
        / "final-uat.sqlite3"
    )


def test_preflight_rejects_wrong_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "companion.uat.canonical_database_path", lambda: Path("/tmp/expected.sqlite3")
    )
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        user_id="uat",
        timezone="Asia/Taipei",
        database_url="sqlite:////tmp/wrong.sqlite3",
    )

    with pytest.raises(UATPreflightError, match="database must be"):
        preflight(settings)


def test_preflight_rejects_database_behind_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path("/tmp/final-uat.sqlite3")
    monkeypatch.setattr("companion.uat.canonical_database_path", lambda: path)
    monkeypatch.setattr(
        "companion.uat.migration_snapshot",
        lambda _: {"current": "old", "head": "head"},
    )
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        user_id="uat",
        timezone="Asia/Taipei",
        database_url=f"sqlite:///{path}",
    )

    with pytest.raises(UATPreflightError, match="not at head"):
        preflight(settings)
