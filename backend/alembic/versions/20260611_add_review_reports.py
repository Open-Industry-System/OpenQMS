"""add review_reports table and report_status columns

Revision ID: 20260611_add_review_reports
Revises: 034_add_supplier_risk_tables
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260611_add_review_reports"
down_revision: Union[str, None] = "034_add_supplier_risk_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "management_reviews",
        sa.Column("report_status", sa.String(20), server_default="none", nullable=False),
    )
    op.create_check_constraint(
        "ck_review_reports_report_status",
        "management_reviews",
        sa.column("report_status").in_(["none", "draft", "final"]),
    )
    op.add_column(
        "management_reviews",
        sa.Column(
            "generated_report",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # Guard: t001_tenant_squash may have already created review_reports via
    # metadata.create_all(CHECKFIRST).  Use IF NOT EXISTS to avoid
    # DuplicateTableError when running after t001.
    conn = op.get_bind()
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS review_reports (
            report_id UUID DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
            review_id UUID NOT NULL REFERENCES management_reviews(review_id) ON DELETE CASCADE,
            version_no INTEGER NOT NULL,
            content JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by UUID NOT NULL REFERENCES users(user_id),
            finalized_by UUID REFERENCES users(user_id),
            finalized_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            UNIQUE (review_id, version_no)
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_review_reports_review_id ON review_reports (review_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_review_reports_created_by ON review_reports (created_by)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_review_reports_finalized_by ON review_reports (finalized_by)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS review_reports"))
    op.drop_column("management_reviews", "generated_report")
    op.drop_column("management_reviews", "report_status")