"""add conversation memory extraction bookkeeping

Revision ID: 20260823_0008
Revises: 20260823_0007
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0008"
down_revision: str | None = "20260823_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "memory_extraction_status",
                sa.String(16),
                nullable=False,
                server_default="not_started",
            )
        )
        batch_op.add_column(
            sa.Column(
                "memory_extraction_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(sa.Column("memory_extraction_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("memory_extracted_at", sa.String(40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("memory_extracted_at")
        batch_op.drop_column("memory_extraction_error")
        batch_op.drop_column("memory_extraction_attempts")
        batch_op.drop_column("memory_extraction_status")
