"""capa cache stage_runs

Revision ID: 20260709_capa_cache_stage_runs
Revises: 20260708_capa_ppt_review_sk
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260709_capa_cache_stage_runs"
down_revision = "20260708_capa_ppt_review_sk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recommendation_cache", sa.Column("stage_runs", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("recommendation_cache", "stage_runs")
