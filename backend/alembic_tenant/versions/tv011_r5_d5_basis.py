"""Persist actual R5 delivered source basis without changing R4b receipts."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from alembic import op

revision = 'tv011_r5_d5_basis'
down_revision = 'tv010_r5_d5_proposals'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('agent_d5_basis_receipts',
        sa.Column('receipt_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('report_id', UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision_id', UUID(as_uuid=True), sa.ForeignKey('capa_d4_root_cause_revisions.revision_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('proof_id', UUID(as_uuid=True), sa.ForeignKey('capa_d4_root_cause_source_proofs.proof_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('lease_epoch', sa.BigInteger(), nullable=False),
        sa.Column('tenant_generation', sa.BigInteger(), nullable=False),
        sa.Column('sources', JSONB(), nullable=False),
        sa.Column('basis_hmac', sa.String(64), nullable=False),
        sa.CheckConstraint('lease_epoch >= 0 AND tenant_generation >= 0', name='ck_d5_basis_epochs'),
        sa.CheckConstraint("jsonb_typeof(sources) = 'array' AND jsonb_array_length(sources) > 0", name='ck_d5_basis_sources'),
        sa.CheckConstraint("basis_hmac ~ '^[0-9a-f]{64}$'", name='ck_d5_basis_hmac'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table('agent_d5_command_basis',
        sa.Column('command_id', UUID(as_uuid=True), sa.ForeignKey('agent_d5_commands.command_id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('receipt_id', UUID(as_uuid=True), sa.ForeignKey('agent_d5_basis_receipts.receipt_id', ondelete='RESTRICT'), primary_key=True),
    )

def downgrade():
    # Refuse before any destructive DDL; receipt evidence is never erased.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM agent_d5_basis_receipts) THEN RAISE EXCEPTION 'nonempty R5 basis receipts'; END IF; END $$")
    op.drop_table('agent_d5_command_basis')
    op.drop_table('agent_d5_basis_receipts')
