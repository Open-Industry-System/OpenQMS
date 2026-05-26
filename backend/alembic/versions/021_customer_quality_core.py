"""add customer quality core tables

Revision ID: 021_customer_quality_core
Revises: 020
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "021_customer_quality_core"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("segment", sa.String(50), nullable=True),
        sa.Column("contact_name", sa.String(100), nullable=True),
        sa.Column("contact_email", sa.String(200), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column(
            "csr_list",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("ppm_target", sa.Float(), nullable=True),
        sa.Column("annual_shipment_qty", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_customers_customer_code", "customers", ["customer_code"])
    op.create_index("ix_customers_name", "customers", ["name"])

    op.create_table(
        "customer_complaints",
        sa.Column("complaint_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("complaint_no", sa.String(50), nullable=False, unique=True),
        sa.Column("product_line_code", sa.String(20), sa.ForeignKey("product_lines.code"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("product_id", sa.String(50), nullable=True),
        sa.Column("batch_no", sa.String(50), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("defect_desc", sa.Text(), nullable=False),
        sa.Column("impact_qty", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("occurred_date", sa.Date(), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("fmea_ref_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fmea_documents.fmea_id"), nullable=True),
        sa.Column("capa_ref_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capa_eightd.report_id"), nullable=True),
        sa.Column("has_rma", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("preliminary_response", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("corrective_action", sa.Text(), nullable=True),
        sa.Column(
            "attachments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("supplier_responsibility", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scar_ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('safety', 'function', 'appearance', 'delivery')",
            name="ck_customer_complaints_category",
        ),
        sa.CheckConstraint(
            "severity IN ('致命', '严重', '一般', '轻微')",
            name="ck_customer_complaints_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'investigating', 'responded', 'closed', 'cancelled')",
            name="ck_customer_complaints_status",
        ),
    )
    op.create_index(
        "ix_customer_complaints_product_line_status",
        "customer_complaints",
        ["product_line_code", "status"],
    )
    op.create_index(
        "ix_customer_complaints_customer_received",
        "customer_complaints",
        ["customer_id", "received_date"],
    )
    op.create_index("ix_customer_complaints_due_date", "customer_complaints", ["due_date"])
    op.create_index("ix_customer_complaints_assignee_id", "customer_complaints", ["assignee_id"])
    op.create_index("ix_customer_complaints_batch_no", "customer_complaints", ["batch_no"])
    op.create_index("ix_customer_complaints_capa_ref_id", "customer_complaints", ["capa_ref_id"])
    op.create_index("ix_customer_complaints_fmea_ref_id", "customer_complaints", ["fmea_ref_id"])

    op.create_table(
        "rma_records",
        sa.Column("rma_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rma_no", sa.String(50), nullable=False, unique=True),
        sa.Column("product_line_code", sa.String(20), sa.ForeignKey("product_lines.code"), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_complaints.complaint_id"),
            nullable=True,
        ),
        sa.Column("product_id", sa.String(50), nullable=True),
        sa.Column("batch_no", sa.String(50), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("return_qty", sa.Integer(), nullable=False),
        sa.Column("defect_type", sa.String(50), nullable=False),
        sa.Column("responsibility", sa.String(50), nullable=True),
        sa.Column("analysis_result", sa.Text(), nullable=True),
        sa.Column("corrective_action", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("fmea_ref_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fmea_documents.fmea_id"), nullable=True),
        sa.Column("capa_ref_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("capa_eightd.report_id"), nullable=True),
        sa.Column("scar_ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "attachments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("tracking_number", sa.String(100), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('open', 'analysis', 'action_pending', 'closed', 'cancelled')",
            name="ck_rma_records_status",
        ),
        sa.CheckConstraint(
            "responsibility IS NULL OR responsibility IN ('supplier', 'internal', 'transport', 'customer_misuse', 'unknown')",
            name="ck_rma_records_responsibility",
        ),
    )
    op.create_index("ix_rma_records_product_line_status", "rma_records", ["product_line_code", "status"])
    op.create_index("ix_rma_records_customer_received", "rma_records", ["customer_id", "received_date"])
    op.create_index("ix_rma_records_complaint_id", "rma_records", ["complaint_id"])
    op.create_index("ix_rma_records_responsibility", "rma_records", ["responsibility"])
    op.create_index("ix_rma_records_assignee_id", "rma_records", ["assignee_id"])
    op.create_index("ix_rma_records_batch_no", "rma_records", ["batch_no"])


def downgrade() -> None:
    op.drop_index("ix_rma_records_batch_no", table_name="rma_records")
    op.drop_index("ix_rma_records_assignee_id", table_name="rma_records")
    op.drop_index("ix_rma_records_responsibility", table_name="rma_records")
    op.drop_index("ix_rma_records_complaint_id", table_name="rma_records")
    op.drop_index("ix_rma_records_customer_received", table_name="rma_records")
    op.drop_index("ix_rma_records_product_line_status", table_name="rma_records")
    op.drop_table("rma_records")

    op.drop_index("ix_customer_complaints_fmea_ref_id", table_name="customer_complaints")
    op.drop_index("ix_customer_complaints_capa_ref_id", table_name="customer_complaints")
    op.drop_index("ix_customer_complaints_batch_no", table_name="customer_complaints")
    op.drop_index("ix_customer_complaints_assignee_id", table_name="customer_complaints")
    op.drop_index("ix_customer_complaints_due_date", table_name="customer_complaints")
    op.drop_index("ix_customer_complaints_customer_received", table_name="customer_complaints")
    op.drop_index("ix_customer_complaints_product_line_status", table_name="customer_complaints")
    op.drop_table("customer_complaints")

    op.drop_index("ix_customers_name", table_name="customers")
    op.drop_index("ix_customers_customer_code", table_name="customers")
    op.drop_table("customers")
