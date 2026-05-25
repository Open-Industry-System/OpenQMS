"""add lock_version to fmea_documents and control_plans for optimistic locking

Revision ID: 019
Revises: 018
Create Date: 2026-05-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('fmea_documents', sa.Column('lock_version', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('control_plans', sa.Column('lock_version', sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('control_plans', 'lock_version')
    op.drop_column('fmea_documents', 'lock_version')
