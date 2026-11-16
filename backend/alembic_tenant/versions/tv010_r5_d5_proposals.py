"""Persist source-bound D5 proposals and command positions; no legacy backfill."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = 'tv010_r5_d5_proposals'
down_revision = 'tv009_r4b_main_merge'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('agent_d5_commands',
        sa.Column('command_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('operation', sa.String(16), nullable=False),
        sa.Column('command_key', sa.String(128), nullable=False),
        sa.Column('request_hmac', sa.String(64), nullable=False),
        sa.Column('sequence', sa.BigInteger(), nullable=False),
        sa.Column('proposal_id', UUID(as_uuid=True), nullable=False),
        sa.UniqueConstraint('task_id', 'command_key', name='uq_d5_command_key'),
        sa.UniqueConstraint('task_id', 'sequence', name='uq_d5_command_sequence'),
        sa.CheckConstraint('sequence > 0', name='ck_d5_command_sequence'),
        sa.CheckConstraint("request_hmac ~ '^[0-9a-f]{64}$'", name='ck_d5_command_hmac'),
        sa.CheckConstraint("operation IN ('save','alternative','replace')", name='ck_d5_command_operation'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table('capa_d5_proposals',
        sa.Column('proposal_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('report_id', UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('original_text', sa.Text(), nullable=False),
        sa.Column('revision_id', UUID(as_uuid=True), sa.ForeignKey('capa_d4_root_cause_revisions.revision_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('proof_id', UUID(as_uuid=True), sa.ForeignKey('capa_d4_root_cause_source_proofs.proof_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('command_id', UUID(as_uuid=True), sa.ForeignKey('agent_d5_commands.command_id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('predecessor_id', UUID(as_uuid=True), sa.ForeignKey('capa_d5_proposals.proposal_id', ondelete='RESTRICT'), nullable=True, unique=True),
        sa.Column('correction_message_id', UUID(as_uuid=True), sa.ForeignKey('agent_task_messages.message_id', ondelete='RESTRICT'), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='RESTRICT'), nullable=False),
        sa.CheckConstraint("state IN ('pending','adopted','withdrawn','superseded')", name='ck_d5_proposal_state'),
        sa.CheckConstraint("octet_length(original_text) BETWEEN 1 AND 16384", name='ck_d5_proposal_text'),
        sa.CheckConstraint('(predecessor_id IS NULL) = (correction_message_id IS NULL)', name='ck_d5_proposal_correction'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table('capa_d5_proposal_sources',
        sa.Column('source_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('proposal_id', UUID(as_uuid=True), sa.ForeignKey('capa_d5_proposals.proposal_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('projection_id', sa.String(160), nullable=False),
        sa.Column('factory_id', UUID(as_uuid=True), sa.ForeignKey('factories.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('product_line_code', sa.String(20), nullable=False),
        sa.Column('fmea_id', UUID(as_uuid=True), nullable=False),
        sa.Column('node_id', sa.String(128), nullable=False),
        sa.Column('node_hmac', sa.String(64), nullable=False),
        sa.UniqueConstraint('proposal_id', 'projection_id', 'fmea_id', 'node_id', name='uq_d5_source_coordinate'),
        sa.CheckConstraint("node_hmac ~ '^[0-9a-f]{64}$'", name='ck_d5_source_hmac'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table('capa_d5_measures',
        sa.Column('measure_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('proposal_id', UUID(as_uuid=True), sa.ForeignKey('capa_d5_proposals.proposal_id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('final_text', sa.Text(), nullable=False),
        sa.Column('adopted_by', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('adopted_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("octet_length(final_text) BETWEEN 1 AND 16384", name='ck_d5_measure_text'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table('capa_d5_withdrawals',
        sa.Column('withdrawal_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('proposal_id', UUID(as_uuid=True), sa.ForeignKey('capa_d5_proposals.proposal_id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='RESTRICT'), nullable=False),
        sa.CheckConstraint("length(trim(reason)) > 0", name='ck_d5_withdrawal_reason'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table('agent_d5_checkpoint_positions',
        sa.Column('checkpoint_id', UUID(as_uuid=True), sa.ForeignKey('agent_d4_recovery_checkpoints.checkpoint_id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('watermark', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('watermark >= 0', name='ck_d5_checkpoint_watermark'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table('capa_d5_staff_receipts',
        sa.Column('receipt_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('operation_key', sa.String(128), nullable=False),
        sa.Column('operation', sa.String(16), nullable=False),
        sa.Column('request_hmac', sa.String(64), nullable=False),
        sa.Column('proposal_id', UUID(as_uuid=True), sa.ForeignKey('capa_d5_proposals.proposal_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('measure_id', UUID(as_uuid=True), sa.ForeignKey('capa_d5_measures.measure_id', ondelete='RESTRICT'), nullable=True),
        sa.Column('withdrawal_id', UUID(as_uuid=True), sa.ForeignKey('capa_d5_withdrawals.withdrawal_id', ondelete='RESTRICT'), nullable=True),
        sa.UniqueConstraint('actor_id', 'operation_key', name='uq_d5_staff_operation_key'),
        sa.CheckConstraint("request_hmac ~ '^[0-9a-f]{64}$'", name='ck_d5_staff_hmac'),
        sa.CheckConstraint("(operation = 'adopt' AND measure_id IS NOT NULL AND withdrawal_id IS NULL) OR (operation = 'withdraw' AND withdrawal_id IS NOT NULL AND measure_id IS NULL)", name='ck_d5_staff_result'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_foreign_key('fk_d5_command_proposal', 'agent_d5_commands', 'capa_d5_proposals', ['proposal_id'], ['proposal_id'], ondelete='RESTRICT', deferrable=True, initially='DEFERRED')

def downgrade():
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM agent_d5_commands)')).scalar():
        raise RuntimeError('R5 D5 evidence exists')
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM capa_d5_proposals)')).scalar():
        raise RuntimeError('R5 D5 evidence exists')
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM capa_d5_proposal_sources)')).scalar():
        raise RuntimeError('R5 D5 evidence exists')
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM capa_d5_measures)')).scalar():
        raise RuntimeError('R5 D5 evidence exists')
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM capa_d5_withdrawals)')).scalar():
        raise RuntimeError('R5 D5 evidence exists')
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM agent_d5_checkpoint_positions)')).scalar():
        raise RuntimeError('R5 D5 evidence exists')
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM capa_d5_staff_receipts)')).scalar():
        raise RuntimeError('R5 D5 evidence exists')
    op.drop_constraint('fk_d5_command_proposal', 'agent_d5_commands', type_='foreignkey')
    op.drop_table('capa_d5_staff_receipts')
    op.drop_table('agent_d5_checkpoint_positions')
    op.drop_table('capa_d5_withdrawals')
    op.drop_table('capa_d5_measures')
    op.drop_table('capa_d5_proposal_sources')
    op.drop_table('capa_d5_proposals')
    op.drop_table('agent_d5_commands')
