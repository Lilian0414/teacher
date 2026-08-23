"""Add embedding model and dimension identity.

Revision ID: 20260823_0009
Revises: 20260823_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0009"
down_revision: str | None = "20260823_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memories", sa.Column("embedding_model", sa.String(256), nullable=True))
    op.add_column("memories", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("memories", "embedding_dimensions")
    op.drop_column("memories", "embedding_model")
