"""create learner preferences

Revision ID: 20260827_0013
Revises: 20260826_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0013"
down_revision: str | None = "20260826_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learner_preferences",
        sa.Column("user_id", sa.String(length=128), primary_key=True),
        sa.Column("correction_style", sa.String(length=16), nullable=False),
        sa.Column("proactive_cadence", sa.String(length=16), nullable=False),
        sa.Column("active_hours_start", sa.String(length=5), nullable=True),
        sa.Column("active_hours_end", sa.String(length=5), nullable=True),
        sa.Column("quiet_hours_start", sa.String(length=5), nullable=True),
        sa.Column("quiet_hours_end", sa.String(length=5), nullable=True),
        sa.Column("practice_balance", sa.String(length=24), nullable=False),
        sa.Column("sound_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "onboarding_state", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("learner_preferences")
