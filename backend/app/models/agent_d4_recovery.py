"""Tenant-local control-only recovery positions for the D4 receiver."""
from datetime import datetime
from uuid import UUID as PyUUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import TenantBase


class D4RecoveryCheckpoint(TenantBase):
    __tablename__ = 'agent_d4_recovery_checkpoints'
    __table_args__ = (
        sa.PrimaryKeyConstraint('checkpoint_id', name='pk_d4_recovery_checkpoint'),
        sa.UniqueConstraint('task_id', 'run_id', 'lease_epoch', name='uq_d4_recovery_position'),
        sa.CheckConstraint('tenant_generation >= 0 AND lease_epoch >= 0 AND accepted_message_seq >= 0', name='ck_d4_recovery_positions'),
        sa.CheckConstraint('update_sequence > 0', name='ck_d4_recovery_update_seq'),
        sa.CheckConstraint("protocol = 'd4-recovery.v1'", name='ck_d4_recovery_protocol'),
        sa.CheckConstraint("resume_position = 'restart_from_start'", name='ck_d4_recovery_resume_position'),
    )
    checkpoint_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False)
    task_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT', name='fk_d4_recovery_checkpoint_task'), nullable=False)
    run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete='RESTRICT', name='fk_d4_recovery_checkpoint_run'), nullable=False)
    task_grant_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_task_grants.grant_id', ondelete='RESTRICT', name='fk_d4_recovery_checkpoint_grant'), nullable=False)
    tenant_generation: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    lease_epoch: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    accepted_message_seq: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    update_sequence: Mapped[int] = mapped_column(sa.BigInteger(), nullable=False)
    protocol: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    resume_position: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    created_by: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='RESTRICT', name='fk_d4_recovery_checkpoint_user'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class D4RecoveryRestart(TenantBase):
    __tablename__ = 'agent_d4_recovery_restarts'
    __table_args__ = (
        sa.PrimaryKeyConstraint('control_id', name='pk_d4_recovery_restart'),
        sa.UniqueConstraint('checkpoint_id', name='uq_d4_recovery_restart_checkpoint'),
        sa.UniqueConstraint('new_run_id', name='uq_d4_recovery_restart_new_run'),
    )
    control_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_task_controls.control_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_control'), primary_key=True, nullable=False)
    checkpoint_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_d4_recovery_checkpoints.checkpoint_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_checkpoint'), nullable=False)
    task_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_task'), nullable=False)
    old_run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_old_run'), nullable=False)
    new_run_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_new_run'), nullable=False)
    start_message_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_task_messages.message_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_message'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class D4TaskParentGrant(TenantBase):
    """Immutable binding from one derived task grant to its authorizing parent."""
    __tablename__ = 'agent_d4_task_parent_grants'
    __table_args__ = (sa.PrimaryKeyConstraint('task_grant_id', name='pk_d4_task_parent_grant'),)
    task_grant_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_task_grants.grant_id', ondelete='RESTRICT', name='fk_d4_parent_task_grant'), primary_key=True, nullable=False)
    plugin_grant_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_plugin_grants.grant_id', ondelete='RESTRICT', name='fk_d4_parent_plugin_grant'), nullable=False)
