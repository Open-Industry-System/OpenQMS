"""make lock_version NOT NULL (was nullable in migration 019)

The ORM model declares lock_version as Mapped[int] (non-nullable) with
default=0, but the migration that added it used nullable=True. This
migration enforces the NOT NULL constraint to match the model.

Revision ID: 037
Revises: 036_factory_id_not_null_enforcement
"""
from alembic import op


revision = '037'
down_revision = '036_factory_id_not_null_enforcement'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('fmea_documents', 'lock_version', nullable=False)
    op.alter_column('control_plans', 'lock_version', nullable=False)


def downgrade() -> None:
    op.alter_column('control_plans', 'lock_version', nullable=True)
    op.alter_column('fmea_documents', 'lock_version', nullable=True)