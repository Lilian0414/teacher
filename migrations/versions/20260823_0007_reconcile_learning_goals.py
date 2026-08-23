"""reconcile duplicate learning goals

Revision ID: 20260823_0007
Revises: 20260822_0006
Create Date: 2026-08-23
"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0007"
down_revision: str | None = "20260822_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _answers(value: str) -> list[str]:
    decoded = json.loads(value)
    return [str(answer) for answer in decoded]


def _merge_answers(rows: list[Any]) -> str:
    merged: list[str] = []
    normalized: set[str] = set()
    for row in rows:
        for answer in _answers(str(row.accepted_answers)):
            key = " ".join(answer.casefold().split())
            if key and key not in normalized:
                normalized.add(key)
                merged.append(answer)
    return json.dumps(merged)


def upgrade() -> None:
    connection = op.get_bind()
    items = sa.table(
        "learning_items",
        sa.column("id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("prompt", sa.Text),
        sa.column("normalized_prompt", sa.Text),
        sa.column("kind", sa.String),
        sa.column("accepted_answers", sa.Text),
        sa.column("source_command", sa.String),
        sa.column("stage", sa.Integer),
        sa.column("next_review_at", sa.String),
        sa.column("created_at", sa.String),
        sa.column("updated_at", sa.String),
    )
    attempts = sa.table(
        "learning_attempts",
        sa.column("learning_item_id", sa.String),
    )
    groups = connection.execute(
        sa.select(items.c.user_id, items.c.normalized_prompt)
        .group_by(items.c.user_id, items.c.normalized_prompt)
        .having(sa.func.count() > 1)
    ).all()
    for user_id, normalized_prompt in groups:
        rows = list(
            connection.execute(
                sa.select(items)
                .where(
                    items.c.user_id == user_id,
                    items.c.normalized_prompt == normalized_prompt,
                )
                .order_by(items.c.created_at, items.c.id)
            ).all()
        )
        survivor, duplicates = rows[0], rows[1:]
        duplicate_ids = [str(row.id) for row in duplicates]
        connection.execute(
            attempts.update()
            .where(attempts.c.learning_item_id.in_(duplicate_ids))
            .values(learning_item_id=survivor.id)
        )
        connection.execute(
            items.update()
            .where(items.c.id == survivor.id)
            .values(
                kind=(
                    "expression"
                    if any(row.kind == "expression" for row in rows)
                    else survivor.kind
                ),
                accepted_answers=_merge_answers(rows),
                stage=min(int(row.stage) for row in rows),
                next_review_at=min(str(row.next_review_at) for row in rows),
                created_at=min(str(row.created_at) for row in rows),
                updated_at=max(str(row.updated_at) for row in rows),
            )
        )
        connection.execute(items.delete().where(items.c.id.in_(duplicate_ids)))

    with op.batch_alter_table(
        "learning_items",
        recreate="always",
        naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"},
    ) as batch_op:
        batch_op.drop_constraint("uq_learning_items_user_id", type_="unique")
        batch_op.create_unique_constraint(
            "uq_learning_items_user_prompt", ["user_id", "normalized_prompt"]
        )


def downgrade() -> None:
    with op.batch_alter_table("learning_items", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_learning_items_user_prompt", type_="unique")
        batch_op.create_unique_constraint(
            "uq_learning_items_user_prompt_kind",
            ["user_id", "normalized_prompt", "kind"],
        )
