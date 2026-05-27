"""add capa_ref_id and resolution_summary to supplier_scars

Revision ID: 022_add_scar_capa
Revises: 021_customer_quality_core, 021 (merge)
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "022_add_scar_capa"
down_revision = ("021_customer_quality_core", "021")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "supplier_scars",
        sa.Column("capa_ref_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_supplier_scars_capa_ref_id",
        "supplier_scars",
        "capa_eightd",
        ["capa_ref_id"],
        ["report_id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "supplier_scars",
        sa.Column("resolution_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("supplier_scars", "resolution_summary")
    op.drop_constraint("fk_supplier_scars_capa_ref_id", "supplier_scars", type_="foreignkey")
    op.drop_column("supplier_scars", "capa_ref_id")
