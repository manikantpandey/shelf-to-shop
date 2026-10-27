"""shop profile, sections, item arrangement and orders

Revision ID: f49d2a442fb0
Revises: 7a932b57480c
Create Date: 2026-10-28 00:31:31.963547
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f49d2a442fb0"
down_revision: str | None = "7a932b57480c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(length=60), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("total_inr", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("paid", sa.Boolean(), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_orders_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("workspace_id", "number", name=op.f("uq_orders_workspace_id")),
    )
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.create_index(
            "ix_orders_workspace_created", ["workspace_id", "created_at"], unique=False
        )

    op.create_table(
        "sections",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name_en", sa.String(length=60), nullable=False),
        sa.Column("name_hi", sa.String(length=60), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_sections_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sections")),
    )
    with op.batch_alter_table("sections", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_sections_workspace_id"), ["workspace_id"], unique=False
        )

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=10), nullable=False, server_default="video")
        )

    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mrp_inr", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("section_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_products_section_id_sections"),
            "sections",
            ["section_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("workspaces", schema=None) as batch_op:
        batch_op.add_column(sa.Column("address", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("hours", sa.String(length=80), nullable=True))
        batch_op.add_column(
            sa.Column("delivery", sa.String(length=10), nullable=False, server_default="pickup")
        )
        batch_op.add_column(sa.Column("delivery_note", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("min_order_inr", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("upi_id", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("about", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("notice", sa.String(length=140), nullable=True))
        batch_op.add_column(sa.Column("logo_key", sa.String(length=300), nullable=True))
        batch_op.add_column(
            sa.Column("order_seq", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("workspaces", schema=None) as batch_op:
        batch_op.drop_column("order_seq")
        batch_op.drop_column("logo_key")
        batch_op.drop_column("notice")
        batch_op.drop_column("about")
        batch_op.drop_column("upi_id")
        batch_op.drop_column("min_order_inr")
        batch_op.drop_column("delivery_note")
        batch_op.drop_column("delivery")
        batch_op.drop_column("hours")
        batch_op.drop_column("address")

    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_products_section_id_sections"), type_="foreignkey")
        batch_op.drop_column("section_id")
        batch_op.drop_column("hidden")
        batch_op.drop_column("featured")
        batch_op.drop_column("mrp_inr")

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("kind")

    with op.batch_alter_table("sections", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sections_workspace_id"))

    op.drop_table("sections")
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_index("ix_orders_workspace_created")

    op.drop_table("orders")
