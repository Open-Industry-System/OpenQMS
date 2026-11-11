"""Add metadata-only tenant-local D4 delivery evidence and exact source scopes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'tv007_d4_text_delivery'
down_revision = 'tv006_agent_read_tasks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'capa_d4_root_cause_revisions',
        sa.Column('revision_id', UUID(as_uuid=True), nullable=False),
        sa.Column('report_id', UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_d4_revision_report_id'), nullable=False),
        sa.Column('revision_no', sa.BigInteger(), nullable=False),
        sa.Column('field_hmac', sa.String(64), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete="RESTRICT", name='fk_d4_revision_actor_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('write_path', sa.String(40), nullable=False),
        sa.PrimaryKeyConstraint('revision_id', name='pk_d4_revision'),
        sa.CheckConstraint('revision_no >= 0', name='ck_d4_revision_no'),
        sa.CheckConstraint("field_hmac ~ '^[0-9a-f]{64}$'", name='ck_d4_revision_field_hmac'),
        sa.UniqueConstraint('report_id', 'revision_no', name='uq_d4_revision_report_no'),
    )
    op.create_table(
        'capa_d4_root_cause_source_proofs',
        sa.Column('proof_id', UUID(as_uuid=True), nullable=False),
        sa.Column('report_id', UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_d4_proof_report_id'), nullable=False),
        sa.Column('revision_id', UUID(as_uuid=True), sa.ForeignKey('capa_d4_root_cause_revisions.revision_id', ondelete="RESTRICT", name='fk_d4_proof_revision_id'), nullable=False),
        sa.Column('verification_id', UUID(as_uuid=True), sa.ForeignKey('capa_root_cause_verification.verification_id', ondelete="RESTRICT", name='fk_d4_proof_verification_id'), nullable=False),
        sa.Column('verification_version', sa.String(64), nullable=False),
        sa.Column('tenant_generation', sa.BigInteger(), nullable=False),
        sa.Column('factory_id', UUID(as_uuid=True), sa.ForeignKey('factories.id', ondelete="RESTRICT", name='fk_d4_proof_factory_id'), nullable=False),
        sa.Column('product_line_code', sa.String(20), nullable=False),
        sa.Column('source_projection_id', sa.String(160), nullable=False),
        sa.Column('fmea_id', UUID(as_uuid=True), nullable=False),
        sa.Column('cause_node_id', sa.String(128), nullable=False),
        sa.Column('node_hmac', sa.String(64), nullable=False),
        sa.Column('field_hmac', sa.String(64), nullable=False),
        sa.Column('declaration_kind', sa.String(40), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('superseded_by', UUID(as_uuid=True), nullable=True),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete="RESTRICT", name='fk_d4_proof_actor_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('invalidated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('proof_id', name='pk_d4_proof'),
        sa.CheckConstraint("verification_version ~ '^[0-9a-f]{64}$'", name='ck_d4_proof_verification_version'),
        sa.CheckConstraint("node_hmac ~ '^[0-9a-f]{64}$'", name='ck_d4_proof_node_hmac'),
        sa.CheckConstraint("field_hmac ~ '^[0-9a-f]{64}$'", name='ck_d4_proof_field_hmac'),
        sa.CheckConstraint('tenant_generation >= 0', name='ck_d4_proof_generation'),
        sa.CheckConstraint("declaration_kind = 'employee_declared_complete_v1'", name='ck_d4_proof_declaration'),
        sa.CheckConstraint("status IN ('active','superseded')", name='ck_d4_proof_status'),
    )
    op.create_index('uq_d4_proof_active_revision', 'capa_d4_root_cause_source_proofs', ['report_id', 'revision_id'], unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_table(
        'agent_restricted_projection_receipts',
        sa.Column('receipt_id', UUID(as_uuid=True), nullable=False),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete="RESTRICT", name='fk_restricted_receipt_task_id'), nullable=False),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('agent_runs.run_id', ondelete="RESTRICT", name='fk_restricted_receipt_run_id'), nullable=False),
        sa.Column('lease_epoch', sa.BigInteger(), nullable=False),
        sa.Column('tenant_generation', sa.BigInteger(), nullable=False),
        sa.Column('source_capa_id', UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_restricted_receipt_source_capa_id'), nullable=False),
        sa.Column('projection_id', sa.String(160), nullable=False),
        sa.Column('projection_digest', sa.String(64), nullable=False),
        sa.Column('data_class', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('receipt_id', name='pk_restricted_receipt'),
        sa.CheckConstraint('lease_epoch >= 0', name='ck_restricted_receipt_epoch'),
        sa.CheckConstraint('tenant_generation >= 0', name='ck_restricted_receipt_generation'),
        sa.CheckConstraint("projection_digest ~ '^[0-9a-f]{64}$'", name='ck_restricted_receipt_projection_digest'),
        sa.CheckConstraint("projection_id = 'capa.d4.root_cause_candidate.masked.v1'", name='ck_restricted_receipt_projection'),
        sa.CheckConstraint("data_class = 'restricted'", name='ck_restricted_receipt_class'),
    )
    op.create_table(
        'agent_plugin_derived_source_scopes',
        sa.Column('scope_id', UUID(as_uuid=True), nullable=False),
        sa.Column('plugin_grant_id', UUID(as_uuid=True), sa.ForeignKey('agent_plugin_grants.grant_id', ondelete="RESTRICT", name='fk_plugin_derived_scope_plugin_grant_id'), nullable=False),
        sa.Column('target_report_id', UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_plugin_derived_scope_target_report_id'), nullable=False),
        sa.Column('derived_projection_id', sa.String(160), nullable=False),
        sa.Column('source_module', sa.String(40), nullable=False),
        sa.Column('source_projection_id', sa.String(160), nullable=False),
        sa.Column('fmea_id', UUID(as_uuid=True), nullable=False),
        sa.Column('cause_node_id', sa.String(128), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete="RESTRICT", name='fk_plugin_derived_scope_actor_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('scope_id', name='pk_plugin_derived_scope'),
        sa.UniqueConstraint('plugin_grant_id', name='uq_plugin_derived_scope_grant'),
    )
    op.create_table(
        'agent_task_derived_source_scopes',
        sa.Column('scope_id', UUID(as_uuid=True), nullable=False),
        sa.Column('task_grant_id', UUID(as_uuid=True), sa.ForeignKey('agent_task_grants.grant_id', ondelete="RESTRICT", name='fk_task_derived_scope_task_grant_id'), nullable=False),
        sa.Column('target_report_id', UUID(as_uuid=True), sa.ForeignKey('capa_eightd.report_id', ondelete="RESTRICT", name='fk_task_derived_scope_target_report_id'), nullable=False),
        sa.Column('derived_projection_id', sa.String(160), nullable=False),
        sa.Column('source_module', sa.String(40), nullable=False),
        sa.Column('source_projection_id', sa.String(160), nullable=False),
        sa.Column('fmea_id', UUID(as_uuid=True), nullable=False),
        sa.Column('cause_node_id', sa.String(128), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete="RESTRICT", name='fk_task_derived_scope_actor_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('scope_id', name='pk_task_derived_scope'),
        sa.UniqueConstraint('task_grant_id', name='uq_task_derived_scope_grant'),
    )
    op.create_table(
        'agent_task_source_requests',
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete="RESTRICT", name='fk_task_source_request_task_id'), nullable=False),
        sa.Column('request_fingerprint', sa.String(64), nullable=False),
        sa.Column('fingerprint_format', sa.String(40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('task_id', name='pk_task_source_request'),
        sa.CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name='ck_task_source_request_request_fingerprint'),
        sa.CheckConstraint("fingerprint_format = 'd4-source-request.v1'", name='ck_task_source_request_format'),
    )


def downgrade() -> None:
    # Refuse before the first DROP, preserving all evidence and the revision.
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM "capa_d4_root_cause_revisions" LIMIT 1)')):
        raise RuntimeError("D4 delivery evidence exists; downgrade refused")
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM "capa_d4_root_cause_source_proofs" LIMIT 1)')):
        raise RuntimeError("D4 delivery evidence exists; downgrade refused")
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM "agent_restricted_projection_receipts" LIMIT 1)')):
        raise RuntimeError("D4 delivery evidence exists; downgrade refused")
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM "agent_plugin_derived_source_scopes" LIMIT 1)')):
        raise RuntimeError("D4 delivery evidence exists; downgrade refused")
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM "agent_task_derived_source_scopes" LIMIT 1)')):
        raise RuntimeError("D4 delivery evidence exists; downgrade refused")
    if connection.scalar(sa.text('SELECT EXISTS (SELECT 1 FROM "agent_task_source_requests" LIMIT 1)')):
        raise RuntimeError("D4 delivery evidence exists; downgrade refused")
    op.drop_table('agent_task_source_requests')
    op.drop_table('agent_task_derived_source_scopes')
    op.drop_table('agent_plugin_derived_source_scopes')
    op.drop_table('agent_restricted_projection_receipts')
    op.drop_table('capa_d4_root_cause_source_proofs')
    op.drop_table('capa_d4_root_cause_revisions')
