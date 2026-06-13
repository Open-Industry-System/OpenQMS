"""add customer audit fields

Revision ID: 025
Revises: 024_add_ppap_fields
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "025"
down_revision = "024_add_ppap_fields"


def upgrade() -> None:
    # audit_plans new columns
    op.add_column("audit_plans", sa.Column(
        "audit_category", sa.String(20), server_default="internal", nullable=False,
    ))
    op.add_column("audit_plans", sa.Column(
        "customer_name", sa.String(200), nullable=True,
    ))
    op.add_column("audit_plans", sa.Column(
        "customer_type", sa.String(50), nullable=True,
    ))
    op.add_column("audit_plans", sa.Column(
        "audit_mode", sa.String(20), nullable=True,
    ))
    op.add_column("audit_plans", sa.Column(
        "customer_confirmation_doc", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False,
    ))

    # CHECK constraints
    op.execute(
        "ALTER TABLE audit_plans ADD CONSTRAINT chk_audit_category "
        "CHECK (audit_category IN ('internal', 'customer', 'supplier'))"
    )
    op.execute(
        "ALTER TABLE audit_plans ADD CONSTRAINT chk_audit_mode "
        "CHECK (audit_mode IS NULL OR audit_mode IN ('on_site', 'remote'))"
    )
    op.execute(
        "ALTER TABLE audit_plans ADD CONSTRAINT chk_customer_type "
        "CHECK (customer_type IS NULL OR customer_type IN ('OEM', 'Tier 1', 'Tier 2', '其他'))"
    )

    op.create_index("idx_audit_plans_category", "audit_plans", ["audit_category"])
    op.create_index("idx_audit_plans_customer_type", "audit_plans", ["customer_type"])
    op.create_index("idx_audit_plans_customer_name", "audit_plans", ["customer_name"])

    # audit_findings new columns
    op.add_column("audit_findings", sa.Column(
        "customer_confirmed", sa.Boolean, server_default="false", nullable=False,
    ))
    op.add_column("audit_findings", sa.Column(
        "customer_confirmation_date", sa.Date, nullable=True,
    ))
    op.add_column("audit_findings", sa.Column(
        "customer_confirmation_attachments", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False,
    ))

    op.create_index("idx_audit_findings_confirmed", "audit_findings", ["customer_confirmed"])

    # capa_ref_id → real FK (clean orphans first)
    op.execute(
        "UPDATE audit_findings SET capa_ref_id = NULL "
        "WHERE capa_ref_id IS NOT NULL "
        "AND capa_ref_id NOT IN (SELECT report_id FROM capa_eightd)"
    )
    op.create_foreign_key(
        "fk_audit_findings_capa", "audit_findings", "capa_eightd",
        ["capa_ref_id"], ["report_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_audit_findings_capa", "audit_findings", type_="foreignkey")

    op.drop_index("idx_audit_findings_confirmed", table_name="audit_findings")
    op.drop_column("audit_findings", "customer_confirmation_attachments")
    op.drop_column("audit_findings", "customer_confirmation_date")
    op.drop_column("audit_findings", "customer_confirmed")

    op.drop_constraint("chk_customer_type", "audit_plans", type_="check")
    op.drop_constraint("chk_audit_mode", "audit_plans", type_="check")
    op.drop_constraint("chk_audit_category", "audit_plans", type_="check")

    op.drop_index("idx_audit_plans_customer_name", table_name="audit_plans")
    op.drop_index("idx_audit_plans_customer_type", table_name="audit_plans")
    op.drop_index("idx_audit_plans_category", table_name="audit_plans")
    op.drop_column("audit_plans", "customer_confirmation_doc")
    op.drop_column("audit_plans", "audit_mode")
    op.drop_column("audit_plans", "customer_type")
    op.drop_column("audit_plans", "customer_name")
    op.drop_column("audit_plans", "audit_category")
