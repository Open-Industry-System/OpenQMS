"""add quality_goals table

Revision ID: 004
Revises: 003
Create Date: 2026-05-21 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quality_goals',
        sa.Column('goal_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('doc_no', sa.String(20), unique=True, nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quality_goals.goal_id'), nullable=True),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('product_line', sa.String(50), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('target_value', sa.String(50), nullable=False),
        sa.Column('actual_value', sa.String(50), nullable=True),
        sa.Column('unit', sa.String(20), nullable=False),
        sa.Column('period', sa.String(20), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('approved_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reject_reason', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_quality_goals_level', 'quality_goals', ['level'])
    op.create_index('ix_quality_goals_status', 'quality_goals', ['status'])
    op.create_index('ix_quality_goals_product_line', 'quality_goals', ['product_line'])


def downgrade() -> None:
    op.drop_index('ix_quality_goals_product_line', table_name='quality_goals')
    op.drop_index('ix_quality_goals_status', table_name='quality_goals')
    op.drop_index('ix_quality_goals_level', table_name='quality_goals')
    op.drop_table('quality_goals')
