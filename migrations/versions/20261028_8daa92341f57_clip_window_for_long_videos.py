"""clip window for long videos

Revision ID: 8daa92341f57
Revises: f49d2a442fb0
Create Date: 2026-10-28 01:07:40.331080
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8daa92341f57"
down_revision: str | None = "f49d2a442fb0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("clip_start_s", sa.Double(), nullable=True))
        batch_op.add_column(sa.Column("clip_len_s", sa.Double(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("clip_len_s")
        batch_op.drop_column("clip_start_s")
