"""add learning signal processing claim lease

Revision ID: 20260830_0015
Revises: 20260829_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0015"
down_revision: str | None = "20260829_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "learning_signal_processing", sa.Column("claim_token", sa.String(36), nullable=True)
    )
    op.add_column(
        "learning_signal_processing",
        sa.Column("lease_expires_at", sa.String(40), nullable=True),
    )
    op.create_index(
        "ix_learning_signal_processing_lease_expires_at",
        "learning_signal_processing",
        ["lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_signal_processing_lease_expires_at",
        table_name="learning_signal_processing",
    )
    op.drop_column("learning_signal_processing", "lease_expires_at")
    op.drop_column("learning_signal_processing", "claim_token")
