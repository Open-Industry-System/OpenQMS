"""Persist source-bound D5 proposals and command positions; no legacy backfill."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from app.database import TenantBase

class AgentD5Command(TenantBase):
    __table__ = sa.Table('agent_d5_commands', TenantBase.metadata,
        sa.Column('command_id', UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('operation', sa.String(16), nullable=False),
        sa.Column('command_key', sa.String(128), nullable=False),
        sa.Column('request_hmac', sa.String(64), nullable=False),
        sa.Column('sequence', sa.BigInteger(), nullable=False),
        sa.Column('proposal_id', UUID(as_uuid=True), sa.ForeignKey('capa_d5_proposals.proposal_id', name='fk_d5_command_proposal', ondelete='RESTRICT', deferrable=True, initially='DEFERRED'), nullable=False),
        sa.UniqueConstraint('task_id', 'command_key', name='uq_d5_command_key'),
        sa.UniqueConstraint('task_id', 'sequence', name='uq_d5_command_sequence'),
        sa.CheckConstraint('sequence > 0', name='ck_d5_command_sequence'),
        sa.CheckConstraint("request_hmac ~ '^[0-9a-f]{64}$'", name='ck_d5_command_hmac'),
        sa.CheckConstraint("operation IN ('save','alternative','replace')", name='ck_d5_command_operation'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

class AgentD5CheckpointPosition(TenantBase):
    __table__ = sa.Table('agent_d5_checkpoint_positions', TenantBase.metadata,
        sa.Column('checkpoint_id', UUID(as_uuid=True), sa.ForeignKey('agent_d4_recovery_checkpoints.checkpoint_id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('watermark', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('watermark >= 0', name='ck_d5_checkpoint_watermark'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

