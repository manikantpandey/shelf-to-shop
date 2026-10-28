"""daily spend totals

Revision ID: e1e6716e856a
Revises: 09af7ba0a0ee
Create Date: 2026-10-29 00:56:35.283293
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1e6716e856a"
down_revision: str | None = "09af7ba0a0ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spend_days",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("micros", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spend_days")),
        sa.UniqueConstraint("scope", "day", name=op.f("uq_spend_days_scope")),
    )


def downgrade() -> None:
    op.drop_table("spend_days")
