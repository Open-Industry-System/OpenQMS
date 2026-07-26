"""add cp_sync_outbox table for durable CP sync on FMEA approval

Revision ID: 20260726_add_cp_sync_outbox
Revises: 20260721_capa_lateral_diffusion
Create Date: 2026-07-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '20260726_add_cp_sync_outbox'
down_revision: Union[str, None] = '20260721_capa_lateral_diffusion'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cp_sync_outbox',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('fmea_id', UUID(as_uuid=True), nullable=False),
        sa.Column('fmea_version_id', UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False, server_default='cp.sync_pending_set'),
        sa.Column('payload', JSONB, nullable=False, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('fmea_id', 'fmea_version_id', 'event_type', name='uq_cp_sync_outbox_event'),
    )
    op.create_index('idx_cp_sync_outbox_pending', 'cp_sync_outbox', ['next_attempt_at'],
                    postgresql_where=sa.text("status = 'pending'"))


def downgrade() -> None:
    op.drop_index('idx_cp_sync_outbox_pending')
    op.drop_table('cp_sync_outbox')
