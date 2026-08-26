"""add proactive conversation practice outcomes

Revision ID: 20260826_0011
Revises: 20260824_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0011"
down_revision: str | None = "20260824_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("proactive_invitations") as batch:
        batch.add_column(sa.Column("conversation_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("user_message_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("assistant_message_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("learning_occurrence_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("learning_item_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("outcome", sa.String(32), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.String(40), nullable=True))
        batch.create_foreign_key(
            "fk_proactive_conversation", "conversations", ["conversation_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_proactive_user_message", "messages", ["user_message_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_proactive_assistant_message", "messages", ["assistant_message_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_proactive_occurrence", "learning_occurrences", ["learning_occurrence_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_proactive_item", "learning_items", ["learning_item_id"], ["id"]
        )
        batch.create_unique_constraint("uq_proactive_user_message", ["user_message_id"])
        batch.create_index("ix_proactive_invitations_conversation_id", ["conversation_id"])


def downgrade() -> None:
    with op.batch_alter_table("proactive_invitations") as batch:
        batch.drop_index("ix_proactive_invitations_conversation_id")
        batch.drop_constraint("uq_proactive_user_message", type_="unique")
        for name in (
            "fk_proactive_item",
            "fk_proactive_occurrence",
            "fk_proactive_assistant_message",
            "fk_proactive_user_message",
            "fk_proactive_conversation",
        ):
            batch.drop_constraint(name, type_="foreignkey")
        for column in (
            "completed_at",
            "outcome",
            "learning_item_id",
            "learning_occurrence_id",
            "assistant_message_id",
            "user_message_id",
            "conversation_id",
        ):
            batch.drop_column(column)
