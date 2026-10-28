"""resumable uploads

Revision ID: 09af7ba0a0ee
Revises: 8daa92341f57
Create Date: 2026-10-28 23:24:53.934601
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "09af7ba0a0ee"
down_revision: str | None = "8daa92341f57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("uploads", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=10), nullable=False, server_default="ready")
        )
        batch_op.add_column(
            sa.Column("received_bytes", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("expected_bytes", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("uploads", schema=None) as batch_op:
        batch_op.drop_column("expected_bytes")
        batch_op.drop_column("received_bytes")
        batch_op.drop_column("status")
