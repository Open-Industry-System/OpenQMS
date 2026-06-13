"""add change_impact_analysis table

Revision ID: 20260602_change_impact
Revises: 20260602_vec_search
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260602_change_impact"
down_revision = "20260602_vec_search"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "change_impact_analysis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("fmea_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_line_code", sa.String(), nullable=False),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("node_type", sa.String(), nullable=False),
        sa.Column("node_name", sa.String(), nullable=False),
        sa.Column("change_type", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(), nullable=False, server_default="single_fmea"),
        sa.Column("status", sa.String(), nullable=False, server_default="completed"),
        sa.Column("impact_score", sa.Integer(), nullable=True),
        sa.Column("impact_result", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_change_impact_fmea", "change_impact_analysis", ["fmea_id"])
    op.create_index("idx_change_impact_node", "change_impact_analysis", ["node_id"])
    op.create_index("idx_change_impact_product_line", "change_impact_analysis", ["product_line_code"])


def downgrade():
    op.drop_index("idx_change_impact_product_line", table_name="change_impact_analysis")
    op.drop_index("idx_change_impact_node", table_name="change_impact_analysis")
    op.drop_index("idx_change_impact_fmea", table_name="change_impact_analysis")
    op.drop_table("change_impact_analysis")
