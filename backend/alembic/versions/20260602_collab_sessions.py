"""add collaboration_sessions table

Revision ID: 20260602_collab_sessions
Revises: 55b6353756f9
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260602_collab_sessions"
down_revision = "55b6353756f9"


def upgrade():
    op.create_table(
        'collaboration_sessions',
        sa.Column('session_id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_type', sa.String(30), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('user_name', sa.String(100), nullable=True),
        sa.Column('action', sa.String(20), server_default='viewing'),
        sa.Column('editing_area', postgresql.JSONB(), nullable=True),
        sa.Column('last_activity', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('session_id'),
        sa.UniqueConstraint('document_type', 'document_id', 'user_id', name='uq_collab_session'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    )
    op.create_index('idx_collab_doc', 'collaboration_sessions', ['document_type', 'document_id'])
    op.create_index('idx_collab_activity', 'collaboration_sessions', ['last_activity'])


def downgrade():
    op.drop_index('idx_collab_activity', table_name='collaboration_sessions')
    op.drop_index('idx_collab_doc', table_name='collaboration_sessions')
    op.drop_table('collaboration_sessions')
