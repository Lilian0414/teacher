import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from companion.learning import LearningRepository
from companion.learning.schemas import LearningKind
from companion.persistence.database import make_engine
from companion.persistence.repositories import decode_dt


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
    assert {"learning_items", "learning_attempts", "learning_occurrences"} <= set(
        inspector.get_table_names()
    )
    memory_columns = {column["name"] for column in inspector.get_columns("memories")}
    assert {"embedding", "embedding_model", "embedding_dimensions"} <= memory_columns

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
    assert "embedding" not in {column["name"] for column in inspector.get_columns("memories")}


def test_duplicate_learning_data_is_reconciled_without_losing_attempts(tmp_path: Path) -> None:
    database_path = tmp_path / "duplicates.sqlite3"
    database_url = f"sqlite:///{database_path}"
    environment = {**os.environ, "COMPANION_DATABASE_URL": database_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "20260822_0006"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    engine = make_engine(database_url)
    with engine.begin() as connection:
        values = {
            "user_id": "default",
            "prompt": "你好",
            "normalized_prompt": "你好",
            "source_command": "help",
            "created_at": "2026-08-01T00:00:00+00:00",
            "updated_at": "2026-08-02T00:00:00+00:00",
        }
        connection.execute(
            text("""INSERT INTO learning_items VALUES
                ('help-id', :user_id, :prompt, :normalized_prompt, 'expression', :help_answers,
                 :source_command, 3, '2026-08-20T00:00:00+00:00', :created_at, :updated_at),
                ('hint-id', :user_id, :prompt, :normalized_prompt, 'phrase', :hint_answers,
                 'hint', 1, '2026-08-10T00:00:00+00:00',
                 '2026-08-02T00:00:00+00:00', '2026-08-03T00:00:00+00:00')"""),
            {
                **values,
                "help_answers": json.dumps(["Hello"]),
                "hint_answers": json.dumps(["Hi", "hello"]),
            },
        )
        connection.execute(
            text("""INSERT INTO learning_attempts VALUES
                ('attempt-help', 'help-id', 'Hello', 1, 0, 1, '2026-08-01T01:00:00+00:00'),
                ('attempt-hint', 'hint-id', 'Hi', 1, 0, 1, '2026-08-02T01:00:00+00:00')""")
        )

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    with engine.connect() as connection:
        item = connection.execute(text("SELECT * FROM learning_items")).mappings().one()
        attempts = connection.execute(text("SELECT * FROM learning_attempts")).mappings().all()
    assert item["id"] == "help-id"
    assert json.loads(item["accepted_answers"]) == ["Hello", "Hi"]
    assert item["stage"] == 1
    assert item["next_review_at"] == "2026-08-10T00:00:00+00:00"
    assert {attempt["learning_item_id"] for attempt in attempts} == {"help-id"}


def test_kind_aware_migration_preserves_legacy_state_and_allows_second_kind(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "kind-aware.sqlite3"
    database_url = f"sqlite:///{database_path}"
    environment = {**os.environ, "COMPANION_DATABASE_URL": database_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "20260826_0011"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO learning_items VALUES
                ('legacy-id', 'default', '我今天很累', '我今天很累', 'expression',
                 '[\"I am tired today.\"]', 'help', 3,
                 '2026-09-10T00:00:00+00:00', '2026-08-01T00:00:00+00:00',
                 '2026-08-05T00:00:00+00:00')""")
        )
        connection.execute(
            text("""INSERT INTO learning_attempts VALUES
                ('attempt-id', 'legacy-id', 'I am tired today.', 1, 2, 3,
                 '2026-08-05T00:00:00+00:00')""")
        )
        connection.execute(
            text("""INSERT INTO learning_occurrences VALUES
                ('occurrence-id', 'legacy-id', 'conversation-id', 'user-message-id',
                 'assistant-message-id', 'correction', '2026-08-01T00:00:00+00:00')""")
        )

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    with Session(engine) as session:
        repository = LearningRepository(session)
        legacy = repository.get_item("legacy-id", user_id="default")
        phrase = repository.upsert_item(
            user_id="default",
            prompt="我今天很累",
            kind=LearningKind.PHRASE,
            accepted_answers=["tired"],
            source_command="hint",
            now=decode_dt("2026-08-26T00:00:00+00:00"),
            first_review_at=decode_dt("2026-08-26T00:00:00+00:00"),
        )
        attempts = repository.attempts_for("legacy-id")
        occurrences = repository.occurrences()
        legacy_state = (
            legacy.id,
            legacy.kind,
            legacy.accepted_answers,
            legacy.stage,
            legacy.next_review_at,
        ) if legacy is not None else None
        phrase_state = (phrase.id, phrase.kind)

    assert legacy_state == (
        "legacy-id",
        "expression",
        '["I am tired today."]',
        3,
        "2026-09-10T00:00:00+00:00",
    )
    assert [attempt.id for attempt in attempts] == ["attempt-id"]
    assert [(item.id, item.learning_item_id) for item in occurrences] == [
        ("occurrence-id", "legacy-id")
    ]
    assert phrase_state[0] != "legacy-id"
    assert phrase_state[1] == "phrase"
