"""create long term memory

Revision ID: 20260719_0003
Revises: 20260719_0002
Create Date: 2026-07-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0003"
down_revision: str | None = "20260719_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("canonical_name", sa.String(length=256, collation="NOCASE"), nullable=False),
        sa.Column("aliases", sa.Text(), nullable=False),
        sa.Column("relationship_to_user", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_name"),
    )
    op.create_index("ix_people_created_at", "people", ["created_at"])

    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=True),
        sa.Column("source_conversation_id", sa.String(length=36), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["people.id"]),
        sa.ForeignKeyConstraint(["source_conversation_id"], ["conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_category", "memories", ["category"])
    op.create_index("ix_memories_created_at", "memories", ["created_at"])
    op.create_index("ix_memories_person_id", "memories", ["person_id"])
    op.create_index("ix_memories_source_conversation_id", "memories", ["source_conversation_id"])
    op.create_index("ix_memories_status", "memories", ["status"])


def downgrade() -> None:
    op.drop_index("ix_memories_status", table_name="memories")
    op.drop_index("ix_memories_source_conversation_id", table_name="memories")
    op.drop_index("ix_memories_person_id", table_name="memories")
    op.drop_index("ix_memories_created_at", table_name="memories")
    op.drop_index("ix_memories_category", table_name="memories")
    op.drop_table("memories")
    op.drop_index("ix_people_created_at", table_name="people")
    op.drop_table("people")
