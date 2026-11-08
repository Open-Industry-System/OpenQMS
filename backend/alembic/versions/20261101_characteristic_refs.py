"""Add characteristic source references.

Revision ID: 20261101_char_refs
Revises: 20260929_agent_read_task
Create Date: 2026-11-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261101_char_refs"
down_revision = "20260929_agent_read_task"
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
