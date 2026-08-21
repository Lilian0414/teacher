"""Create proactive invitation ledger.

Revision ID: 20260821_0005
Revises: 20260810_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0005"
down_revision: str | None = "20260810_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proactive_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("responded_at", sa.String(40), nullable=True),
        sa.Column("suppress_until", sa.String(40), nullable=True),
        sa.Column("local_date", sa.String(10), nullable=False),
        sa.Column("starter_key", sa.String(64), nullable=True),
        sa.Column("starter_prompt", sa.Text(), nullable=True),
    )
    op.create_index("ix_proactive_invitations_user_id", "proactive_invitations", ["user_id"])
    op.create_index("ix_proactive_invitations_status", "proactive_invitations", ["status"])
    op.create_index("ix_proactive_pending", "proactive_invitations", ["user_id", "status"])
    op.create_index("ix_proactive_daily", "proactive_invitations", ["user_id", "local_date"])


def downgrade() -> None:
    op.drop_table("proactive_invitations")
