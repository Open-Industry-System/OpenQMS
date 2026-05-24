"""add product_lines table

Revision ID: 011_add_product_lines
Revises: 07b2479d1321
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa

revision = "011_add_product_lines"
down_revision = "07b2479d1321"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_lines",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("product_lines")
