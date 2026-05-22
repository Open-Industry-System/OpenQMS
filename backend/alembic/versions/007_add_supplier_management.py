"""add supplier management

Revision ID: 007_add_supplier_management
Revises: 006_add_audit_doc_nos
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "suppliers",
        sa.Column("supplier_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_no", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(100), nullable=False),
        sa.Column("contact_name", sa.String(100), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("product_scope", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_review"),
        sa.Column("audit_plan_id", UUID(as_uuid=True), sa.ForeignKey("audit_plans.audit_id", ondelete="SET NULL"), nullable=True),
        sa.Column("reject_reason", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_suppliers_status", "suppliers", ["status"])
    op.create_index("ix_suppliers_name", "suppliers", ["name"])
    op.create_index("ix_suppliers_short_name", "suppliers", ["short_name"])

    op.create_table(
        "supplier_certifications",
        sa.Column("cert_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("cert_type", sa.String(100), nullable=False),
        sa.Column("cert_no", sa.String(100), nullable=False),
        sa.Column("issued_by", sa.String(255), nullable=True),
        sa.Column("issue_date", sa.Date, nullable=True),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_supplier_certs_supplier_id", "supplier_certifications", ["supplier_id"])
    op.create_index("ix_supplier_certs_expiry", "supplier_certifications", ["expiry_date"])

    op.create_table(
        "supplier_evaluations",
        sa.Column("eval_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("eval_period", sa.String(20), nullable=False),
        sa.Column("eval_type", sa.String(20), nullable=False),
        sa.Column("quality_score", sa.Float, nullable=False),
        sa.Column("delivery_score", sa.Float, nullable=False),
        sa.Column("service_score", sa.Float, nullable=False),
        sa.Column("capa_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("finding_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("capa_penalty", sa.Float, nullable=False, server_default="0"),
        sa.Column("finding_penalty", sa.Float, nullable=False, server_default="0"),
        sa.Column("total_score", sa.Float, nullable=False),
        sa.Column("grade", sa.String(1), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("evaluated_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_supplier_evals_supplier_id", "supplier_evaluations", ["supplier_id"])


def downgrade():
    op.drop_index("ix_supplier_evals_supplier_id", table_name="supplier_evaluations")
    op.drop_table("supplier_evaluations")
    op.drop_index("ix_supplier_certs_expiry", table_name="supplier_certifications")
    op.drop_index("ix_supplier_certs_supplier_id", table_name="supplier_certifications")
    op.drop_table("supplier_certifications")
    op.drop_index("ix_suppliers_short_name", table_name="suppliers")
    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_index("ix_suppliers_status", table_name="suppliers")
    op.drop_table("suppliers")
