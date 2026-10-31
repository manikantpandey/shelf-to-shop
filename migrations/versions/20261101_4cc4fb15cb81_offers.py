"""offers

Revision ID: 4cc4fb15cb81
Revises: e1e6716e856a
Create Date: 2026-11-01 04:19:13.867137
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4cc4fb15cb81"
down_revision: str | None = "e1e6716e856a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "offers",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("title_en", sa.String(length=80), nullable=False),
        sa.Column("title_hi", sa.String(length=80), nullable=True),
        sa.Column("percent_off", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.Column("item_ids", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["sections.id"],
            name=op.f("fk_offers_section_id_sections"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_offers_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offers")),
    )
    with op.batch_alter_table("offers", schema=None) as batch_op:
        batch_op.create_index(
            "ix_offers_workspace_created", ["workspace_id", "created_at"], unique=False
        )
        # Partial unique index (SQLite and Postgres both support it): one running offer per shop.
        batch_op.create_index(
            "uq_offers_running_workspace",
            ["workspace_id"],
            unique=True,
            sqlite_where=sa.text("ended_at IS NULL"),
            postgresql_where=sa.text("ended_at IS NULL"),
        )


def downgrade() -> None:
    with op.batch_alter_table("offers", schema=None) as batch_op:
        batch_op.drop_index("uq_offers_running_workspace")
        batch_op.drop_index("ix_offers_workspace_created")

    op.drop_table("offers")
