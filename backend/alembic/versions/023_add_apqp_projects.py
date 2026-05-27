"""add apqp_projects table

Revision ID: 023_add_apqp_projects
Revises: 022_add_scar_capa
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "023_add_apqp_projects"
down_revision = "022_add_scar_capa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "apqp_projects",
        sa.Column("project_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_code", sa.String(30), unique=True, nullable=False),
        sa.Column("project_name", sa.String(200), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("customer_name", sa.String(200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_sop_date", sa.Date(), nullable=True),
        sa.Column("team_members", JSONB(), nullable=True),
        sa.Column("current_phase", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("phase_status", sa.String(20), nullable=True, server_default="in_progress"),
        sa.Column("project_status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("phase_1_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_2_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_3_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_4_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_5_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gate_approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("gate_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gate_comments", sa.Text(), nullable=True),
        sa.Column("gate_history", JSONB(), nullable=True),
        sa.Column("dfmea_id", UUID(as_uuid=True), nullable=True),
        sa.Column("pfmea_id", UUID(as_uuid=True), nullable=True),
        sa.Column("control_plan_id", UUID(as_uuid=True), nullable=True),
        sa.Column("ppap_submission_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indexes
    op.create_index("ix_apqp_projects_project_status", "apqp_projects", ["project_status"])
    op.create_index("ix_apqp_projects_current_phase", "apqp_projects", ["current_phase"])

    # Foreign keys
    op.create_foreign_key("fk_apqp_projects_product_line", "apqp_projects", "product_lines", ["product_line_code"], ["code"])
    op.create_foreign_key("fk_apqp_projects_gate_approved_by", "apqp_projects", "users", ["gate_approved_by"], ["user_id"])
    op.create_foreign_key("fk_apqp_projects_created_by", "apqp_projects", "users", ["created_by"], ["user_id"])
    op.create_foreign_key("fk_apqp_projects_dfmea_id", "apqp_projects", "fmea_documents", ["dfmea_id"], ["fmea_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_apqp_projects_pfmea_id", "apqp_projects", "fmea_documents", ["pfmea_id"], ["fmea_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_apqp_projects_control_plan_id", "apqp_projects", "control_plans", ["control_plan_id"], ["cp_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_apqp_projects_ppap_submission_id", "apqp_projects", "supplier_ppap_submissions", ["ppap_submission_id"], ["submission_id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_table("apqp_projects")
