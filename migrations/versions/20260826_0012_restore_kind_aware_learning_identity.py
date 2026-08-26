"""restore kind-aware learning-item identity

Revision ID: 20260826_0012
Revises: 20260826_0011

Legacy rows are intentionally left untouched. Their stored kind remains the only
provenance available; future captures with another kind can create a new item.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260826_0012"
down_revision: str | None = "20260826_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("learning_items", recreate="always") as batch:
        batch.drop_constraint("uq_learning_items_user_prompt", type_="unique")
        batch.create_unique_constraint(
            "uq_learning_items_user_prompt_kind",
            ["user_id", "normalized_prompt", "kind"],
        )


def downgrade() -> None:
    with op.batch_alter_table("learning_items", recreate="always") as batch:
        batch.drop_constraint("uq_learning_items_user_prompt_kind", type_="unique")
        batch.create_unique_constraint(
            "uq_learning_items_user_prompt", ["user_id", "normalized_prompt"]
        )
