"""add product_types table and product_lines.product_type_code

Revision ID: 20260624_add_product_types
Revises: 20260617_rec_cache_idx
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa


revision = "20260624_add_product_types"
down_revision = "20260617_rec_cache_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_types",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("product_lines", sa.Column("product_type_code", sa.String(20), nullable=True))
    op.create_foreign_key(
        "fk_product_lines_product_type",
        "product_lines", "product_types",
        ["product_type_code"], ["code"], ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_product_lines_product_type", "product_lines", type_="foreignkey")
    op.drop_column("product_lines", "product_type_code")
    op.drop_table("product_types")
