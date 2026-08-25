"""Add durable conversation learning provenance.

Revision ID: 20260824_0010
Revises: 20260823_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0010"
down_revision: str | None = "20260823_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_occurrences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "learning_item_id", sa.String(36), sa.ForeignKey("learning_items.id"), nullable=False
        ),
        sa.Column(
            "source_conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column(
            "source_user_message_id", sa.String(36), sa.ForeignKey("messages.id"), nullable=False
        ),
        sa.Column(
            "source_assistant_message_id",
            sa.String(36),
            sa.ForeignKey("messages.id"),
            nullable=False,
        ),
        sa.Column("acceptance_reason", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("source_user_message_id"),
    )
    op.create_index(
        "ix_learning_occurrences_learning_item_id", "learning_occurrences", ["learning_item_id"]
    )
    op.create_index(
        "ix_learning_occurrences_source_conversation_id",
        "learning_occurrences",
        ["source_conversation_id"],
    )
    op.create_index(
        "ix_learning_occurrences_source_user_message_id",
        "learning_occurrences",
        ["source_user_message_id"],
    )
    op.create_index(
        "ix_learning_occurrences_source_assistant_message_id",
        "learning_occurrences",
        ["source_assistant_message_id"],
    )


def downgrade() -> None:
    op.drop_table("learning_occurrences")
