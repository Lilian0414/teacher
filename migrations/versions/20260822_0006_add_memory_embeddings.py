"""Add provider-neutral embedding persistence to memories.

Revision ID: 20260822_0006
Revises: 20260821_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0006"
down_revision: str | None = "20260821_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memories", sa.Column("embedding", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("memories", "embedding")
