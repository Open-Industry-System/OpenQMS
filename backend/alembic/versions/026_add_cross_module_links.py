"""add cross-module link fields

Revision ID: 026
Revises: 025
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CAPA -> FMEA failure mode node-level linking
    op.add_column(
        "capa_eightd",
        sa.Column("fmea_node_id", sa.String(36), nullable=True),
    )

    # Complaint -> Supplier linking
    op.add_column(
        "customer_complaints",
        sa.Column(
            "supplier_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.supplier_id"),
            nullable=True,
        ),
    )

    # Special characteristic citation links
    op.create_table(
        "special_characteristic_links",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sc_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("special_characteristics.sc_id"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("source_item_id", sa.String(36), nullable=False),
    )
    op.create_unique_constraint(
        "uq_sc_link",
        "special_characteristic_links",
        ["sc_id", "source_type", "source_id", "source_item_id"],
    )


def downgrade() -> None:
    op.drop_table("special_characteristic_links")
    op.drop_column("customer_complaints", "supplier_id")
    op.drop_column("capa_eightd", "fmea_node_id")
