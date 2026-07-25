"""Add capa_d7_node_action.status column (US-E2E-01.3)

Revision ID: 20260708_d7_node_action_status
Revises: 20260707_d7_null_fmea
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20260708_d7_node_action_status"
down_revision = "20260707_d7_null_fmea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL 在单语句内加 NOT NULL DEFAULT 列时，用默认值回填所有现存行
    op.add_column(
        "capa_d7_node_action",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
    )


def downgrade() -> None:
    op.drop_column("capa_d7_node_action", "status")
