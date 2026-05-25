"""add refresh_token columns to users

Revision ID: 018
Revises: 017
Create Date: 2026-05-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('refresh_token', sa.String(500), nullable=True))
    op.add_column('users', sa.Column('refresh_token_expires', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'refresh_token_expires')
    op.drop_column('users', 'refresh_token')
