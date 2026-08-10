"""create availability overrides

Revision ID: 20260719_0001
Revises:
Create Date: 2026-07-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "availability_overrides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_availability_overrides_expires_at",
        "availability_overrides",
        ["expires_at"],
    )
    op.create_index("ix_availability_overrides_state", "availability_overrides", ["state"])
    op.create_index("ix_availability_overrides_user_id", "availability_overrides", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_availability_overrides_user_id", table_name="availability_overrides")
    op.drop_index("ix_availability_overrides_state", table_name="availability_overrides")
    op.drop_index("ix_availability_overrides_expires_at", table_name="availability_overrides")
    op.drop_table("availability_overrides")
