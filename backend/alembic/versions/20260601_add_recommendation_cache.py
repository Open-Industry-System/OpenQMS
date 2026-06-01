"""add recommendation_cache table

Revision ID: 20260601_rec_cache
Revises: 028_permission_matrix
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "20260601_rec_cache"
down_revision = "028_permission_matrix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_cache",
        sa.Column("cache_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("fmea_id", UUID(as_uuid=True), sa.ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("fmea_type", sa.String(20), nullable=False),
        sa.Column("suggestions", JSONB, nullable=False),
        sa.Column("source", sa.String(15), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), server_default=sa.text("now() + INTERVAL '24 hours'"), nullable=False),
        sa.UniqueConstraint("fmea_id", "trigger_type", "context_hash", name="uq_recommendation_cache_lookup"),
    )
    op.create_index("ix_recommendation_cache_lookup", "recommendation_cache", ["fmea_id", "trigger_type", "context_hash", "expires_at"])
    op.create_index("ix_recommendation_cache_expires", "recommendation_cache", ["expires_at"])


def downgrade() -> None:
    op.drop_table("recommendation_cache")
