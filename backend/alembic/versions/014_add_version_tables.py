"""add version tables for FMEA and Control Plan

Revision ID: 014_add_version_tables
Revises: 013_add_management_review
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014_add_version_tables"
down_revision = "013_add_management_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create fmea_versions table
    op.create_table(
        "fmea_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "fmea_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("major_no", sa.Integer, nullable=False),
        sa.Column("minor_no", sa.Integer, nullable=False),
        sa.Column("snapshot", postgresql.JSONB, nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("change_type", sa.String(20), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("fmea_id", "major_no", "minor_no", name="uq_fmea_versions_version"),
    )
    op.create_index(
        "ix_fmea_versions_fmea_created",
        "fmea_versions",
        ["fmea_id", sa.text("created_at DESC")],
    )

    # Create control_plan_versions table
    op.create_table(
        "control_plan_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cp_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("control_plans.cp_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("major_no", sa.Integer, nullable=False),
        sa.Column("minor_no", sa.Integer, nullable=False),
        sa.Column("header_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("items_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column(
            "source_fmea_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fmea_versions.version_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("change_type", sa.String(20), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("cp_id", "major_no", "minor_no", name="uq_cp_versions_version"),
    )
    op.create_index(
        "ix_cp_versions_cp_created",
        "control_plan_versions",
        ["cp_id", sa.text("created_at DESC")],
    )

    # Alter control_plans table
    op.add_column(
        "control_plans",
        sa.Column(
            "source_fmea_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fmea_versions.version_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "control_plans",
        sa.Column("sync_pending", sa.Boolean, server_default="false", nullable=False),
    )

    # Alter control_plan_items table
    op.add_column(
        "control_plan_items",
        sa.Column("item_source", sa.String(20), server_default="fmea", nullable=False),
    )


def downgrade() -> None:
    # Revert control_plan_items changes
    op.drop_column("control_plan_items", "item_source")

    # Revert control_plans changes
    op.drop_column("control_plans", "sync_pending")
    op.drop_column("control_plans", "source_fmea_version_id")

    # Drop control_plan_versions table
    op.drop_index("ix_cp_versions_cp_created", table_name="control_plan_versions")
    op.drop_table("control_plan_versions")

    # Drop fmea_versions table
    op.drop_index("ix_fmea_versions_fmea_created", table_name="fmea_versions")
    op.drop_table("fmea_versions")