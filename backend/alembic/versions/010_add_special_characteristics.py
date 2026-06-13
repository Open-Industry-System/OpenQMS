"""add special_characteristics table

Revision ID: 010_special_chars
Revises: 009_add_msa_tables
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
import uuid

revision = "010_special_chars"
down_revision = "009_add_msa_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "special_characteristics",
        sa.Column("sc_id", sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("sc_code", sa.String(32), unique=True, nullable=False),
        sa.Column("sc_name", sa.String(200), nullable=False),
        sa.Column("sc_type", sa.String(4), nullable=False),
        sa.Column("customer_symbol", sa.String(32), nullable=True),
        sa.Column("sc_category", sa.String(20), nullable=True),
        sa.Column("spec_requirement", sa.Text, nullable=True),
        sa.Column("parent_sc_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("source_fmea_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("source_node_id", sa.String(36), nullable=False),
        sa.Column("source_type", sa.String(10), nullable=False),
        sa.Column("cp_item_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("msa_study_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("msa_status", sa.String(20), nullable=True, server_default="PENDING"),
        sa.Column("sop_ref", sa.String(200), nullable=True),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("is_supplier_shared", sa.Boolean, nullable=True, server_default=sa.text("false")),
        sa.Column("supplier_code", sa.String(50), nullable=True),
        sa.Column("created_by", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.CheckConstraint("sc_type IN ('CC', 'SC')", name="ck_sc_type"),
        sa.CheckConstraint("source_type IN ('DFMEA', 'PFMEA')", name="ck_source_type"),
        sa.ForeignKeyConstraint(["parent_sc_id"], ["special_characteristics.sc_id"], name="fk_sc_parent"),
        sa.ForeignKeyConstraint(["source_fmea_id"], ["fmea_documents.fmea_id"], name="fk_sc_fmea"),
        sa.ForeignKeyConstraint(["cp_item_id"], ["control_plan_items.item_id"], name="fk_sc_cp_item"),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], name="fk_sc_creator"),
    )


def downgrade() -> None:
    op.drop_table("special_characteristics")
