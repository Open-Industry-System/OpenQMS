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

    op.create_table(
        "review_reports",
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "review_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("management_reviews.review_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "finalized_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
            index=True,
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("review_id", "version_no", name="uq_review_reports_review_version"),
    )


def downgrade() -> None:
    op.drop_table("review_reports")
    op.drop_column("management_reviews", "generated_report")
    op.drop_column("management_reviews", "report_status")
