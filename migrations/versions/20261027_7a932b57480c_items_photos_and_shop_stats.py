"""items, photos and shop stats

Revision ID: 7a932b57480c
Revises: ead722453a5d
Create Date: 2026-10-27 23:22:28.436078
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a932b57480c"
down_revision: str | None = "ead722453a5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shop_counters",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("item_id", sa.String(length=80), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_shop_counters_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shop_counters")),
        sa.UniqueConstraint(
            "workspace_id", "day", "kind", "item_id", name=op.f("uq_shop_counters_workspace_id")
        ),
    )
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("image_source", sa.String(length=20), nullable=False, server_default="video")
        )
        batch_op.add_column(sa.Column("image_credit", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("image_credit_url", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("first_seen_s", sa.Double(), nullable=True))
        batch_op.add_column(sa.Column("last_seen_s", sa.Double(), nullable=True))
        batch_op.add_column(sa.Column("best_frame_s", sa.Double(), nullable=True))
        batch_op.add_column(
            sa.Column("sold_out", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    with op.batch_alter_table("workspaces", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("workspaces", schema=None) as batch_op:
        batch_op.drop_column("is_template")

    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_column("sold_out")
        batch_op.drop_column("best_frame_s")
        batch_op.drop_column("last_seen_s")
        batch_op.drop_column("first_seen_s")
        batch_op.drop_column("image_credit_url")
        batch_op.drop_column("image_credit")
        batch_op.drop_column("image_source")

    op.drop_table("shop_counters")
