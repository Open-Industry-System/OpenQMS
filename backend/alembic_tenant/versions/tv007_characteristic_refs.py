"""Add characteristic source references.

Revision ID: tv007_characteristic_refs
Revises: tv006_agent_read_tasks
Create Date: 2026-11-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "tv007_characteristic_refs"
down_revision = "tv006_agent_read_tasks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "control_plan_items",
        sa.Column("source_characteristic_ref", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "special_characteristics",
        sa.Column("source_characteristic_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade():
    op.drop_column("special_characteristics", "source_characteristic_id")
    op.drop_column("control_plan_items", "source_characteristic_ref")
