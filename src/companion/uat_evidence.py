"""Read-only, secret-safe evidence snapshot for the final manual UAT."""

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from alembic.config import Config
from alembic.script import ScriptDirectory

from companion.settings import Settings, get_settings


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=False, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def _database_revision(path: Path | None) -> str:
    if path is None:
        return "not-sqlite"
    if not path.exists():
        return "database-not-found"
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return f"unavailable ({type(exc).__name__})"
    return str(row[0]) if row else "no-current-revision"


def _alembic_head() -> str:
    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    return ",".join(heads) if heads else "none"


def migration_snapshot(path: Path | None) -> dict[str, str]:
    """Return the current and expected revisions without modifying the database."""
    return {"head": _alembic_head(), "current": _database_revision(path)}


def configuration_snapshot(settings: Settings) -> dict[str, object]:
    """Return allow-listed settings only; credential values are never included."""
    return {
        "user_id": settings.user_id,
        "timezone": settings.timezone,
        "core_url": settings.core_url,
        "llm_provider": settings.llm_provider,
        "groq_model": settings.groq_model,
        "groq_api_key": "present (redacted)" if settings.groq_api_key else "not set",
        "embeddings_enabled": settings.embeddings_enabled,
        "embedding_base_url": settings.embedding_base_url,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "embedding_api_key": "present (redacted)" if settings.embedding_api_key else "not set",
        "database_path": str(settings.sqlite_path) if settings.sqlite_path else "non-SQLite URL",
    }


def _get_json(url: str) -> dict[str, Any] | str:
    try:
        with urlopen(url, timeout=2) as response:
            payload = json.load(response)
    except (OSError, TimeoutError, URLError, json.JSONDecodeError) as exc:
        return f"unavailable ({type(exc).__name__})"
    return payload if isinstance(payload, dict) else "unexpected response"


def evidence_snapshot(settings: Settings) -> dict[str, object]:
    """Collect configuration, migration, and read-only Core evidence."""
    return {
        "commit": _git_commit(),
        "configuration": configuration_snapshot(settings),
        "alembic": migration_snapshot(settings.sqlite_path),
        "core": {
            "health": _get_json(f"{settings.core_url}/health"),
            "state": _get_json(f"{settings.core_url}/v1/state"),
        },
    }


def main() -> None:
    """Print a JSON evidence snapshot without mutating product state."""
    print(json.dumps(evidence_snapshot(get_settings()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
