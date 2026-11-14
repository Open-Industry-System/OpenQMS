"""Add control-only D4 recovery positions and restart associations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'tv008_d4_recovery'
down_revision = 'tv007_d4_text_delivery'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_d4_recovery_checkpoints',
        sa.Column('checkpoint_id', UUID(as_uuid=True), nullable=False),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT', name='fk_d4_recovery_checkpoint_task'), nullable=False),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete='RESTRICT', name='fk_d4_recovery_checkpoint_run'), nullable=False),
        sa.Column('task_grant_id', UUID(as_uuid=True), sa.ForeignKey('agent_task_grants.grant_id', ondelete='RESTRICT', name='fk_d4_recovery_checkpoint_grant'), nullable=False),
        sa.Column('tenant_generation', sa.BigInteger(), nullable=False),
        sa.Column('lease_epoch', sa.BigInteger(), nullable=False),
        sa.Column('accepted_message_seq', sa.BigInteger(), nullable=False),
        sa.Column('update_sequence', sa.BigInteger(), nullable=False),
        sa.Column('protocol', sa.String(32), nullable=False),
        sa.Column('resume_position', sa.String(32), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='RESTRICT', name='fk_d4_recovery_checkpoint_user'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('checkpoint_id', name='pk_d4_recovery_checkpoint'),
        sa.UniqueConstraint('task_id', 'run_id', 'lease_epoch', name='uq_d4_recovery_position'),
        sa.CheckConstraint('tenant_generation >= 0 AND lease_epoch >= 0 AND accepted_message_seq >= 0', name='ck_d4_recovery_positions'),
        sa.CheckConstraint('update_sequence > 0', name='ck_d4_recovery_update_seq'),
        sa.CheckConstraint("protocol = 'd4-recovery.v1'", name='ck_d4_recovery_protocol'),
        sa.CheckConstraint("resume_position = 'restart_from_start'", name='ck_d4_recovery_resume_position'),
    )
    op.create_table(
        'agent_d4_recovery_restarts',
        sa.Column('control_id', UUID(as_uuid=True), sa.ForeignKey('agent_task_controls.control_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_control'), nullable=False),
        sa.Column('checkpoint_id', UUID(as_uuid=True), sa.ForeignKey('agent_d4_recovery_checkpoints.checkpoint_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_checkpoint'), nullable=False),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_task'), nullable=False),
        sa.Column('old_run_id', UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_old_run'), nullable=False),
        sa.Column('new_run_id', UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_new_run'), nullable=False),
        sa.Column('start_message_id', UUID(as_uuid=True), sa.ForeignKey('agent_task_messages.message_id', ondelete='RESTRICT', name='fk_d4_recovery_restart_message'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('control_id', name='pk_d4_recovery_restart'),
        sa.UniqueConstraint('checkpoint_id', name='uq_d4_recovery_restart_checkpoint'),
        sa.UniqueConstraint('new_run_id', name='uq_d4_recovery_restart_new_run'),
    )

    op.create_table(
        'agent_d4_task_parent_grants',
        sa.Column('task_grant_id', UUID(as_uuid=True), sa.ForeignKey('agent_task_grants.grant_id', ondelete='RESTRICT', name='fk_d4_parent_task_grant'), nullable=False),
        sa.Column('plugin_grant_id', UUID(as_uuid=True), sa.ForeignKey('agent_plugin_grants.grant_id', ondelete='RESTRICT', name='fk_d4_parent_plugin_grant'), nullable=False),
        sa.PrimaryKeyConstraint('task_grant_id', name='pk_d4_task_parent_grant'),
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM "agent_d4_recovery_checkpoints")')).scalar():
        raise RuntimeError('D4 recovery evidence exists')
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM "agent_d4_recovery_restarts")')).scalar():
        raise RuntimeError('D4 recovery evidence exists')
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM "agent_d4_task_parent_grants")')).scalar():
        raise RuntimeError('D4 recovery evidence exists')
    op.drop_table('agent_d4_task_parent_grants')
    op.drop_table('agent_d4_recovery_restarts')
    op.drop_table('agent_d4_recovery_checkpoints')
