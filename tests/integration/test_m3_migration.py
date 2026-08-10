import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect

from companion.persistence.database import make_engine


def test_m3_migration_upgrades_and_downgrades(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.sqlite3"
    environment = {
        **os.environ,
        "COMPANION_DATABASE_URL": f"sqlite:///{database_path}",
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    inspector = inspect(make_engine(f"sqlite:///{database_path}"))
    assert {"learning_items", "learning_attempts"} <= set(inspector.get_table_names())

    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "20260719_0003"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    inspector = inspect(make_engine(f"sqlite:///{database_path}"))
    assert "learning_items" not in inspector.get_table_names()
    assert "memories" in inspector.get_table_names()
