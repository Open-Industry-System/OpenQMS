"""spc v1.1: attribute charts and control limit versioning

Revision ID: 008_spc_v1_1
Revises: 007_add_supplier_management
Create Date: 2026-05-22
"""
from alembic import op
import sqlalchemy as sa

revision = '008_spc_v1_1'
down_revision = '007_add_supplier_management'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # sample_batches: add attribute chart columns
    op.add_column('sample_batches', sa.Column('inspected_count', sa.Integer(), nullable=True))
    op.add_column('sample_batches', sa.Column('defect_count', sa.Integer(), nullable=True))

    # control_limit_snapshots: add versioning columns
    op.add_column('control_limit_snapshots', sa.Column('version_no', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('control_limit_snapshots', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('control_limit_snapshots', 'is_active')
    op.drop_column('control_limit_snapshots', 'version_no')
    op.drop_column('sample_batches', 'defect_count')
    op.drop_column('sample_batches', 'inspected_count')
