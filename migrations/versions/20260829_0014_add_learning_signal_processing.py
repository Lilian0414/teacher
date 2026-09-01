"""add durable learning signal processing ledger

Revision ID: 20260829_0014
Revises: 20260827_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0014"
down_revision: str | None = "20260827_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_signal_processing",
        sa.Column("user_message_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("assistant_message_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("status_detail", sa.String(160), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("last_attempted_at", sa.String(40), nullable=True),
        sa.Column("completed_at", sa.String(40), nullable=True),
        sa.ForeignKeyConstraint(["assistant_message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["user_message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("user_message_id"),
        sa.UniqueConstraint("assistant_message_id"),
    )
    op.create_index(
        "ix_learning_signal_processing_conversation_id",
        "learning_signal_processing",
        ["conversation_id"],
    )
    op.create_index(
        "ix_learning_signal_processing_status", "learning_signal_processing", ["status"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_signal_processing_status", table_name="learning_signal_processing"
    )
    op.drop_index(
        "ix_learning_signal_processing_conversation_id",
        table_name="learning_signal_processing",
    )
    op.drop_table("learning_signal_processing")
