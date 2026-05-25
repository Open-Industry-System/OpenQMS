"""add management review tables

Revision ID: 013_add_management_review
Revises: 012_add_safety_fields_to_sc
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "013_add_management_review"
down_revision = "012_add_safety_fields_to_sc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "management_reviews",
        sa.Column("review_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("review_date", sa.Date, nullable=False),
        sa.Column("actual_date", sa.Date, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "product_line_code",
            sa.String(20),
            sa.ForeignKey("product_lines.code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column(
            "chair_person_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column("participants", postgresql.JSONB, nullable=True),
        sa.Column("meeting_minutes", sa.Text, nullable=True),
        sa.Column("data_package", postgresql.JSONB, nullable=True),
        sa.Column("manual_inputs", postgresql.JSONB, nullable=True),
        sa.Column("attachments", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column(
            "updated_by",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'data_collected', 'in_review', 'closed')",
            name="ck_mgmt_reviews_status",
        ),
    )
    op.create_index("ix_mgmt_reviews_status", "management_reviews", ["status"])
    op.create_index(
        "ix_mgmt_reviews_product_line", "management_reviews", ["product_line_code"]
    )

    op.create_table(
        "review_outputs",
        sa.Column("output_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "review_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("management_reviews.review_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "responsible_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("completion_notes", sa.Text, nullable=True),
        sa.Column(
            "verified_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column("verified_at", sa.Date, nullable=True),
        sa.Column("verification_notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('improvement_opportunity', 'system_change', 'resource_need')",
            name="ck_review_outputs_category",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'verified')",
            name="ck_review_outputs_status",
        ),
    )
    op.create_index("ix_review_outputs_review_id", "review_outputs", ["review_id"])


def downgrade() -> None:
    op.drop_table("review_outputs")
    op.drop_table("management_reviews")
