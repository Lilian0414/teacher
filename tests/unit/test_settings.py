from pathlib import Path

import pytest

from companion.persistence.database import make_engine
from companion.settings import Settings


def test_default_groq_model_is_supported_replacement() -> None:
    assert Settings().groq_model == "openai/gpt-oss-20b"


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
