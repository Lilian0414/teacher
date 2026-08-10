"""create learning loop

Revision ID: 20260810_0004
Revises: 20260719_0003
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0004"
down_revision: str | None = "20260719_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("normalized_prompt", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("accepted_answers", sa.Text(), nullable=False),
        sa.Column("source_command", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("next_review_at", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "normalized_prompt", "kind"),
    )
    op.create_index("ix_learning_items_user_id", "learning_items", ["user_id"])
    op.create_index("ix_learning_items_next_review_at", "learning_items", ["next_review_at"])
    op.create_index(
        "ix_learning_items_due",
        "learning_items",
        ["user_id", "next_review_at", "created_at"],
    )
    op.create_table(
        "learning_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("learning_item_id", sa.String(length=36), nullable=False),
        sa.Column("submitted_answer", sa.Text(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("stage_before", sa.Integer(), nullable=False),
        sa.Column("stage_after", sa.Integer(), nullable=False),
        sa.Column("attempted_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["learning_item_id"], ["learning_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_learning_attempts_learning_item_id", "learning_attempts", ["learning_item_id"]
    )
    op.create_index(
        "ix_learning_attempts_history",
        "learning_attempts",
        ["learning_item_id", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_attempts_history", table_name="learning_attempts")
    op.drop_index("ix_learning_attempts_learning_item_id", table_name="learning_attempts")
    op.drop_table("learning_attempts")
    op.drop_index("ix_learning_items_due", table_name="learning_items")
    op.drop_index("ix_learning_items_next_review_at", table_name="learning_items")
    op.drop_index("ix_learning_items_user_id", table_name="learning_items")
    op.drop_table("learning_items")
