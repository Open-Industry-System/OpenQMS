"""R6 tenant-local source and history contracts.

Origins are integrity metadata, never an authorization grant. Source-owner
services must reauthorize each typed coordinate before loading any body.
Original R5 receipts and proof formats deliberately remain untouched.
"""
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import TenantBase


def _id(name, target=None, *, primary_key=False, nullable=False):
    args = [name, UUID(as_uuid=True)]
    if target:
        args.append(sa.ForeignKey(target, ondelete='RESTRICT'))
    return sa.Column(*args, primary_key=primary_key, nullable=nullable,
                     **({'default': uuid4} if primary_key else {}))


def _created():
    return sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _text_check(column, name, *, empty=False):
    expression = f'octet_length({column}) <= 16384'
    if not empty:
        expression += f' AND length(btrim({column})) > 0'
    return sa.CheckConstraint(expression, name=name)


# Additive unique keys let R6 use report/task composite relationships without
# changing the existing R5 fields, JSON serializers, or signed declarations.
EXISTING_UNIQUES = (
    ('agent_tasks', 'uq_r6_task_report', ('task_id', 'target_capa_id')),
    ('agent_runs', 'uq_r6_run_task', ('run_id', 'task_id')),
    ('agent_task_messages', 'uq_r6_message_task', ('message_id', 'task_id')),
    ('capa_d4_root_cause_revisions', 'uq_r6_root_report', ('revision_id', 'report_id')),
    ('agent_d5_basis_receipts', 'uq_r6_basis_root', ('receipt_id', 'report_id', 'revision_id')),
    ('agent_d4_recovery_checkpoints', 'uq_r6_checkpoint_task', ('checkpoint_id', 'task_id')),
)
for _table, _name, _columns in EXISTING_UNIQUES:
    _target = TenantBase.metadata.tables[_table]
    sa.UniqueConstraint(*(_target.c[column] for column in _columns), name=_name)


class CapaR6MaterialVersion(TenantBase):
    __table__ = sa.Table('capa_r6_material_versions', TenantBase.metadata,
        _id('report_id', 'capa_eightd.report_id', primary_key=True),
        sa.Column('counter', sa.BigInteger(), nullable=False, server_default='0'),
        sa.CheckConstraint('counter >= 0', name='ck_r6_material_counter'), _created())


class CapaR6EntrySwitch(TenantBase):
    __table__ = sa.Table('capa_r6_entry_switches', TenantBase.metadata,
        _id('switch_id', primary_key=True),
        sa.Column('epoch', sa.BigInteger(), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        _id('actor_id', 'users.user_id'),
        sa.Column('evidence', JSONB(), nullable=False),
        sa.UniqueConstraint('epoch', name='uq_r6_switch_epoch'),
        sa.CheckConstraint('epoch >= 0', name='ck_r6_switch_epoch'),
        sa.CheckConstraint("state IN ('legacy','draining','switched')", name='ck_r6_switch_state'),
        sa.CheckConstraint("jsonb_typeof(evidence) = 'object'", name='ck_r6_switch_evidence'), _created())


class CapaR6ReportSnapshot(TenantBase):
    __table__ = sa.Table('capa_r6_report_snapshots', TenantBase.metadata,
        _id('snapshot_id', primary_key=True), _id('report_id', 'capa_eightd.report_id'),
        sa.Column('kind', sa.String(8), nullable=False),
        sa.Column('version', sa.BigInteger(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.UniqueConstraint('snapshot_id', 'report_id', name='uq_r6_snapshot_report'),
        sa.UniqueConstraint('report_id', 'kind', 'version', name='uq_r6_snapshot_version'),
        sa.CheckConstraint("kind IN ('d2','d3')", name='ck_r6_snapshot_kind'),
        sa.CheckConstraint('version >= 0', name='ck_r6_snapshot_version'),
        _created())


class CapaR6SourceOrigin(TenantBase):
    __table__ = sa.Table('capa_r6_source_origins', TenantBase.metadata,
        _id('source_id', primary_key=True), _id('report_id', 'capa_eightd.report_id'),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('module', sa.String(16), nullable=False), _id('object_id'),
        sa.Column('projection_id', sa.String(160), nullable=False),
        sa.Column('version', sa.String(128), nullable=False),
        sa.Column('source_version_counter', sa.BigInteger(), nullable=True),
        sa.CheckConstraint("source_version_counter IS NULL OR (kind = 'fmea_projection' AND source_version_counter >= 0)", name='ck_r6_source_version_counter'),
        _id('factory_id', 'factories.id'),
        sa.Column('product_line_code', sa.String(20), nullable=False),
        _id('snapshot_id', nullable=True),
        _id('fmea_id', 'fmea_documents.fmea_id', nullable=True),
        sa.Column('node_id', sa.String(128)),
        sa.ForeignKeyConstraint(['snapshot_id', 'report_id'],
            ['capa_r6_report_snapshots.snapshot_id', 'capa_r6_report_snapshots.report_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('source_id', 'report_id', name='uq_r6_origin_report'),
        sa.CheckConstraint("(kind = 'report_snapshot' AND module = 'capa' AND object_id = report_id AND snapshot_id IS NOT NULL AND fmea_id IS NULL AND node_id IS NULL AND projection_id IN ('capa.d2.snapshot.v1','capa.d3.snapshot.v1')) OR (kind = 'fmea_projection' AND module = 'fmea' AND object_id = fmea_id AND snapshot_id IS NULL AND fmea_id IS NOT NULL AND node_id IS NOT NULL AND projection_id = 'fmea.failure_cause.reference.v1')", name='ck_r6_origin_coordinate'),
        sa.CheckConstraint('length(version) > 0', name='ck_r6_origin_version'), _created())


class AgentD4CandidateCommand(TenantBase):
    __table__ = sa.Table('agent_d4_candidate_commands', TenantBase.metadata,
        _id('command_id', primary_key=True), _id('report_id', 'capa_eightd.report_id'),
        _id('task_id'), _id('run_id'),
        sa.Column('command_key', sa.String(128), nullable=False),
        sa.Column('operation', sa.String(16), nullable=False),
        sa.Column('sequence', sa.BigInteger(), nullable=False),
        sa.Column('request_hmac', sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(['task_id', 'report_id'], ['agent_tasks.task_id', 'agent_tasks.target_capa_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['run_id', 'task_id'], ['agent_runs.run_id', 'agent_runs.task_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('task_id', 'command_key', name='uq_d4_candidate_command_key'),
        sa.UniqueConstraint('task_id', 'sequence', name='uq_d4_candidate_command_sequence'),
        sa.UniqueConstraint('command_id', 'report_id', 'task_id', 'run_id', name='uq_d4_candidate_command_target'),
        sa.CheckConstraint('sequence > 0', name='ck_d4_candidate_sequence'),
        sa.CheckConstraint("command_key ~ '^[A-Za-z0-9._:-]{1,128}$'", name='ck_d4_candidate_command_key'),
        sa.CheckConstraint("request_hmac ~ '^[0-9a-f]{64}$'", name='ck_d4_candidate_command_hmac'),
        sa.CheckConstraint("operation IN ('save','alternative','replace')", name='ck_d4_candidate_operation'), _created())


class AgentD4CandidateCheckpointPosition(TenantBase):
    __table__ = sa.Table('agent_d4_candidate_checkpoint_positions', TenantBase.metadata,
        _id('checkpoint_id', primary_key=True),
        _id('task_id', 'agent_tasks.task_id'),
        sa.Column('watermark', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['checkpoint_id', 'task_id'], ['agent_d4_recovery_checkpoints.checkpoint_id', 'agent_d4_recovery_checkpoints.task_id'], ondelete='RESTRICT'),
        sa.CheckConstraint('watermark >= 0', name='ck_d4_candidate_checkpoint_watermark'), _created())


class CapaD4Candidate(TenantBase):
    __table__ = sa.Table('capa_d4_candidates', TenantBase.metadata,
        _id('candidate_id', primary_key=True), _id('report_id', 'capa_eightd.report_id'),
        _id('task_id'), _id('run_id'), _id('command_id'),
        sa.Column('original_text', sa.Text(), nullable=False),
        sa.Column('supporting', JSONB(), nullable=False),
        sa.Column('opposing', JSONB(), nullable=False),
        sa.Column('missing_information', JSONB(), nullable=False),
        sa.Column('input_versions', JSONB(), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('version', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('source_count', sa.Integer(), nullable=False, server_default='1'),
        _id('predecessor_id', nullable=True), _id('correction_message_id', nullable=True),
        _id('created_by', 'users.user_id'),
        sa.ForeignKeyConstraint(['command_id', 'report_id', 'task_id', 'run_id'],
            ['agent_d4_candidate_commands.command_id', 'agent_d4_candidate_commands.report_id', 'agent_d4_candidate_commands.task_id', 'agent_d4_candidate_commands.run_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['predecessor_id', 'report_id', 'task_id'],
            ['capa_d4_candidates.candidate_id', 'capa_d4_candidates.report_id', 'capa_d4_candidates.task_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['correction_message_id', 'task_id'], ['agent_task_messages.message_id', 'agent_task_messages.task_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('candidate_id', 'report_id', name='uq_d4_candidate_report'),
        sa.UniqueConstraint('candidate_id', 'report_id', 'task_id', name='uq_d4_candidate_task'),
        sa.UniqueConstraint('command_id', name='uq_d4_candidate_command'),
        sa.UniqueConstraint('predecessor_id', name='uq_d4_candidate_successor'),
        sa.CheckConstraint("state IN ('pending','adopted','withdrawn','superseded')", name='ck_d4_candidate_state'),
        sa.CheckConstraint('version > 0', name='ck_d4_candidate_version'),
        sa.CheckConstraint('source_count > 0', name='ck_d4_candidate_source_count'),
        sa.CheckConstraint('(predecessor_id IS NULL) = (correction_message_id IS NULL) AND predecessor_id IS DISTINCT FROM candidate_id', name='ck_d4_candidate_correction'),
        sa.CheckConstraint("jsonb_typeof(supporting) = 'array' AND jsonb_typeof(opposing) = 'array' AND jsonb_typeof(missing_information) = 'array' AND jsonb_typeof(input_versions) = 'object'", name='ck_d4_candidate_evidence'),
        _text_check('original_text', 'ck_d4_candidate_text'), _created())


class CapaD4CandidateSource(TenantBase):
    __table__ = sa.Table('capa_d4_candidate_sources', TenantBase.metadata,
        _id('candidate_id', primary_key=True), _id('report_id'), _id('source_id', primary_key=True),
        sa.ForeignKeyConstraint(['candidate_id', 'report_id'], ['capa_d4_candidates.candidate_id', 'capa_d4_candidates.report_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_id', 'report_id'], ['capa_r6_source_origins.source_id', 'capa_r6_source_origins.report_id'], ondelete='RESTRICT'), _created())


class CapaR6RootRevisionBody(TenantBase):
    __table__ = sa.Table('capa_r6_root_revision_bodies', TenantBase.metadata,
        _id('revision_id', primary_key=True), _id('report_id'),
        sa.Column('binding_state', sa.String(24), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        _id('predecessor_id', nullable=True),
        sa.Column('source_count', sa.Integer(), nullable=False),
        sa.Column('origin_digest', sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(['revision_id', 'report_id'], ['capa_d4_root_cause_revisions.revision_id', 'capa_d4_root_cause_revisions.report_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['predecessor_id', 'report_id'], ['capa_r6_root_revision_bodies.revision_id', 'capa_r6_root_revision_bodies.report_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('revision_id', 'report_id', name='uq_r6_root_body_report'),
        sa.CheckConstraint("(binding_state = 'controlled' AND source_count > 0) OR (binding_state = 'legacy_unattested' AND source_count = 0)", name='ck_r6_root_binding'),
        sa.CheckConstraint("origin_digest ~ '^[0-9a-f]{64}$'", name='ck_r6_root_digest'),
        sa.CheckConstraint('predecessor_id IS DISTINCT FROM revision_id', name='ck_r6_root_predecessor'),
        _created())


class CapaR6RootRevisionSource(TenantBase):
    __table__ = sa.Table('capa_r6_root_revision_sources', TenantBase.metadata,
        _id('revision_id', primary_key=True), _id('report_id'), _id('source_id', primary_key=True),
        sa.ForeignKeyConstraint(['revision_id', 'report_id'], ['capa_r6_root_revision_bodies.revision_id', 'capa_r6_root_revision_bodies.report_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_id', 'report_id'], ['capa_r6_source_origins.source_id', 'capa_r6_source_origins.report_id'], ondelete='RESTRICT'), _created())


class CapaD5MeasureRevision(TenantBase):
    __table__ = sa.Table('capa_d5_measure_revisions', TenantBase.metadata,
        _id('revision_id', primary_key=True), _id('report_id', 'capa_eightd.report_id'),
        _id('measure_id', 'capa_d5_measures.measure_id'),
        sa.Column('revision_no', sa.BigInteger(), nullable=False),
        _id('predecessor_id', nullable=True),
        sa.Column('final_text', sa.Text(), nullable=False), sa.Column('reason', sa.Text(), nullable=False),
        _id('actor_id', 'users.user_id'),
        sa.ForeignKeyConstraint(['predecessor_id', 'measure_id'], ['capa_d5_measure_revisions.revision_id', 'capa_d5_measure_revisions.measure_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('revision_id', 'measure_id', name='uq_d5_measure_revision_measure'),
        sa.UniqueConstraint('revision_id', 'report_id', name='uq_d5_measure_revision_report'),
        sa.UniqueConstraint('measure_id', 'revision_no', name='uq_d5_measure_revision_no'),
        sa.UniqueConstraint('predecessor_id', name='uq_d5_measure_revision_successor'),
        sa.CheckConstraint("revision_no > 0 AND ((revision_no = 1 AND predecessor_id IS NULL) OR (revision_no > 1 AND predecessor_id IS NOT NULL))", name='ck_d5_measure_revision_predecessor'),
        _text_check('final_text', 'ck_d5_measure_revision_text'), _text_check('reason', 'ck_d5_measure_revision_reason'), _created())


class CapaR6StaffReceipt(TenantBase):
    __table__ = sa.Table('capa_r6_staff_receipts', TenantBase.metadata,
        _id('receipt_id', primary_key=True), _id('actor_id', 'users.user_id'),
        sa.Column('operation_key', sa.String(128), nullable=False),
        sa.Column('operation', sa.String(24), nullable=False), sa.Column('request_hmac', sa.String(64), nullable=False),
        _id('report_id', 'capa_eightd.report_id'),
        _id('candidate_id', nullable=True), _id('root_revision_id', nullable=True), _id('measure_revision_id', nullable=True),
        sa.ForeignKeyConstraint(['candidate_id', 'report_id'], ['capa_d4_candidates.candidate_id', 'capa_d4_candidates.report_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['root_revision_id', 'report_id'], ['capa_r6_root_revision_bodies.revision_id', 'capa_r6_root_revision_bodies.report_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['measure_revision_id', 'report_id'], ['capa_d5_measure_revisions.revision_id', 'capa_d5_measure_revisions.report_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('actor_id', 'operation_key', name='uq_r6_staff_operation_key'),
        sa.CheckConstraint("operation_key ~ '^[A-Za-z0-9._:-]{1,128}$'", name='ck_r6_staff_operation_key'),
        sa.CheckConstraint("request_hmac ~ '^[0-9a-f]{64}$'", name='ck_r6_staff_hmac'),
        sa.CheckConstraint("(operation = 'd4_confirm' AND candidate_id IS NOT NULL AND root_revision_id IS NOT NULL AND measure_revision_id IS NULL) OR (operation = 'd4_withdraw' AND candidate_id IS NOT NULL AND root_revision_id IS NULL AND measure_revision_id IS NULL) OR (operation = 'd5_correct' AND measure_revision_id IS NOT NULL AND candidate_id IS NULL AND root_revision_id IS NULL)", name='ck_r6_staff_result'), _created())


class CapaR6RootDeliveryBinding(TenantBase):
    __table__ = sa.Table('capa_r6_root_delivery_bindings', TenantBase.metadata,
        _id('receipt_id', primary_key=True), _id('report_id'), _id('revision_id'),
        sa.Column('origin_digest', sa.String(64), nullable=False),
        sa.Column('input_bindings', JSONB(), nullable=False),
        sa.Column('binding_hmac', sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(['receipt_id', 'report_id', 'revision_id'], ['agent_d5_basis_receipts.receipt_id', 'agent_d5_basis_receipts.report_id', 'agent_d5_basis_receipts.revision_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['revision_id', 'report_id'], ['capa_r6_root_revision_bodies.revision_id', 'capa_r6_root_revision_bodies.report_id'], ondelete='RESTRICT'),
        sa.CheckConstraint("origin_digest ~ '^[0-9a-f]{64}$' AND binding_hmac ~ '^[0-9a-f]{64}$'", name='ck_r6_delivery_digests'),
        sa.CheckConstraint("jsonb_typeof(input_bindings) = 'array'", name='ck_r6_delivery_inputs'), _created())


class AgentD4InputReceipt(TenantBase):
    __table__ = sa.Table('agent_d4_input_receipts', TenantBase.metadata,
        _id('receipt_id', primary_key=True), _id('report_id'), _id('task_id'), _id('run_id'),
        _id('executor_id', 'users.user_id'), _id('installation_id', 'agent_plugin_installations.installation_id'),
        _id('deployment_id', 'agent_model_deployments.deployment_id'),
        sa.Column('lease_epoch', sa.BigInteger(), nullable=False),
        sa.Column('tenant_generation', sa.BigInteger(), nullable=False),
        sa.Column('deployment_config_hmac', sa.String(64), nullable=False),
        sa.Column('source_count', sa.Integer(), nullable=False),
        sa.Column('input_versions', JSONB(), nullable=False),
        sa.Column('receipt_hmac', sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(['task_id', 'report_id'], ['agent_tasks.task_id', 'agent_tasks.target_capa_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['run_id', 'task_id'], ['agent_runs.run_id', 'agent_runs.task_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('receipt_id', 'report_id', name='uq_d4_input_report'),
        sa.UniqueConstraint('receipt_id', 'report_id', 'task_id', 'run_id', name='uq_d4_input_target'),
        sa.CheckConstraint('lease_epoch >= 0 AND tenant_generation >= 0 AND source_count BETWEEN 3 AND 64', name='ck_d4_input_counts'),
        sa.CheckConstraint("deployment_config_hmac ~ '^[0-9a-f]{64}$' AND receipt_hmac ~ '^[0-9a-f]{64}$' AND jsonb_typeof(input_versions) = 'object'", name='ck_d4_input_hmac'), _created())


class AgentD4InputReceiptSource(TenantBase):
    __table__ = sa.Table('agent_d4_input_receipt_sources', TenantBase.metadata,
        _id('receipt_id', primary_key=True), _id('report_id'), _id('source_id', primary_key=True),
        sa.ForeignKeyConstraint(['receipt_id', 'report_id'], ['agent_d4_input_receipts.receipt_id', 'agent_d4_input_receipts.report_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_id', 'report_id'], ['capa_r6_source_origins.source_id', 'capa_r6_source_origins.report_id'], ondelete='RESTRICT'), _created())


class AgentD4CommandInput(TenantBase):
    __table__ = sa.Table('agent_d4_command_inputs', TenantBase.metadata,
        _id('command_id', primary_key=True), _id('receipt_id', primary_key=True),
        _id('report_id'), _id('task_id'), _id('run_id'),
        sa.ForeignKeyConstraint(['command_id', 'report_id', 'task_id', 'run_id'], ['agent_d4_candidate_commands.command_id', 'agent_d4_candidate_commands.report_id', 'agent_d4_candidate_commands.task_id', 'agent_d4_candidate_commands.run_id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['receipt_id', 'report_id', 'task_id', 'run_id'], ['agent_d4_input_receipts.receipt_id', 'agent_d4_input_receipts.report_id', 'agent_d4_input_receipts.task_id', 'agent_d4_input_receipts.run_id'], ondelete='RESTRICT'), _created())


class CapaD4CandidateWithdrawal(TenantBase):
    __table__ = sa.Table('capa_d4_candidate_withdrawals', TenantBase.metadata,
        _id('receipt_id', 'capa_r6_staff_receipts.receipt_id', primary_key=True),
        _id('candidate_id'), _id('report_id'), sa.Column('reason', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id', 'report_id'], ['capa_d4_candidates.candidate_id', 'capa_d4_candidates.report_id'], ondelete='RESTRICT'),
        _text_check('reason', 'ck_d4_withdraw_reason'), _created())


R6_TABLES = tuple(table.name for table in TenantBase.metadata.tables.values()
                  if table.name.startswith(('capa_r6_', 'agent_d4_candidate_', 'agent_d4_input_', 'agent_d4_command_inputs', 'capa_d4_candidate'))
                  or table.name == 'capa_d5_measure_revisions')


class CapaR6LocalRevision(TenantBase):
    __table__ = sa.Table('capa_r6_local_revisions', TenantBase.metadata,
        _id('revision_id', primary_key=True), _id('report_id', 'capa_eightd.report_id'),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('revision_no', sa.BigInteger(), nullable=False), _id('predecessor_id', nullable=True),
        _id('actor_id', 'users.user_id'), _id('analysis_id', 'capa_docg_analysis.analysis_id', nullable=True),
        _id('root_snapshot_revision_id',nullable=True),
        sa.ForeignKeyConstraint(['root_snapshot_revision_id','report_id'],['capa_r6_root_revision_bodies.revision_id','capa_r6_root_revision_bodies.report_id'],ondelete='RESTRICT',name='fk_r6_local_snapshot_root'),
        sa.CheckConstraint('(source_count=0) = (root_snapshot_revision_id IS NOT NULL)',name='ck_r6_local_snapshot_count'),
        sa.Column('operation_key', sa.String(128), nullable=False),
        sa.Column('request_hmac', sa.String(64), nullable=False),
        sa.Column('text', sa.Text(), nullable=True), sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('basis', sa.Text(), nullable=True),
        sa.Column('input_bindings', JSONB(), nullable=False),
        sa.Column('candidates', JSONB(), nullable=False), sa.Column('channels', JSONB(none_as_null=True), nullable=True),
        sa.Column('source_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['predecessor_id','report_id','kind'],
            ['capa_r6_local_revisions.revision_id','capa_r6_local_revisions.report_id','capa_r6_local_revisions.kind'], ondelete='RESTRICT'),
        sa.UniqueConstraint('revision_id','report_id','kind',name='uq_r6_local_kind'),
        sa.UniqueConstraint('revision_id','report_id',name='uq_r6_local_report'),
        sa.UniqueConstraint('report_id','kind','revision_no',name='uq_r6_local_revision'),
        sa.UniqueConstraint('predecessor_id',name='uq_r6_local_successor'),
        sa.UniqueConstraint('actor_id','operation_key',name='uq_r6_local_operation'),
        sa.UniqueConstraint('analysis_id',name='uq_r6_local_analysis'),
        sa.CheckConstraint("kind IN ('prevention','manual_analysis','propagation')",name='ck_r6_local_kind'),
        sa.CheckConstraint("revision_no > 0 AND ((revision_no=1 AND predecessor_id IS NULL) OR (revision_no>1 AND predecessor_id IS NOT NULL))",name='ck_r6_local_predecessor'),
        sa.CheckConstraint("operation_key ~ '^[A-Za-z0-9._:-]{1,128}$' AND request_hmac ~ '^[0-9a-f]{64}$'",name='ck_r6_local_receipt'),
        sa.CheckConstraint("(kind='manual_analysis') = (analysis_id IS NOT NULL)",name='ck_r6_local_analysis'),
        sa.CheckConstraint("(kind='prevention' AND text IS NOT NULL AND basis IS NOT NULL AND octet_length(text)<=16384 AND length(btrim(text))>0 AND octet_length(basis)<=16384 AND length(btrim(basis))>0) OR (kind<>'prevention' AND text IS NULL AND basis IS NULL)",name='ck_r6_local_body'),
        sa.CheckConstraint("(kind='propagation' AND channels IS NOT NULL AND channels = '{\"lessons\":\"NOT_EXECUTED\",\"knowledge\":\"NOT_EXECUTED\",\"lateral\":\"NOT_EXECUTED\",\"supplier_risk\":\"NOT_EXECUTED\"}'::jsonb) OR (kind<>'propagation' AND channels IS NULL)",name='ck_r6_local_channels'),
        sa.CheckConstraint("source_count >= 0 AND jsonb_typeof(input_bindings)='object' AND octet_length(input_bindings::text)<=262144 AND jsonb_typeof(candidates)='array' AND octet_length(candidates::text)<=262144",name='ck_r6_local_inputs'),
        _text_check('reason','ck_r6_local_reason'), _created())


class CapaR6LocalSource(TenantBase):
    __table__ = sa.Table('capa_r6_local_sources', TenantBase.metadata,
        _id('revision_id',primary_key=True), _id('report_id'),
        sa.Column('module',sa.String(16),primary_key=True), _id('object_id',primary_key=True),
        _id('factory_id','factories.id'), sa.Column('product_line_code',sa.String(20),nullable=False),
        sa.ForeignKeyConstraint(['revision_id','report_id'],['capa_r6_local_revisions.revision_id','capa_r6_local_revisions.report_id'],ondelete='RESTRICT'),
        sa.CheckConstraint("module IN ('fmea','planning') AND length(btrim(product_line_code))>0",name='ck_r6_local_source'), _created())

R6_TABLES = (*R6_TABLES, 'capa_r6_local_revisions', 'capa_r6_local_sources')


class CapaR6ManualDecisionReceipt(TenantBase):
    __table__=sa.Table('capa_r6_manual_decision_receipts',TenantBase.metadata,
        _id('receipt_id',primary_key=True),_id('actor_id','users.user_id'),
        _id('report_id','capa_eightd.report_id'),_id('analysis_id','capa_docg_analysis.analysis_id'),
        _id('decision_id','capa_docg_decision.decision_id'),
        sa.Column('operation',sa.String(16),nullable=False),sa.Column('operation_key',sa.String(128),nullable=False),
        sa.Column('request_hmac',sa.String(64),nullable=False),
        sa.UniqueConstraint('actor_id','operation_key',name='uq_r6_manual_decision_key'),
        sa.UniqueConstraint('decision_id',name='uq_r6_manual_decision_result'),
        sa.CheckConstraint("operation IN ('audit','defer','no_affected','waiver')",name='ck_r6_manual_decision_operation'),
        sa.CheckConstraint("operation_key ~ '^[A-Za-z0-9._:-]{1,128}$' AND request_hmac ~ '^[0-9a-f]{64}$'",name='ck_r6_manual_decision_receipt'),_created())
R6_TABLES=(*R6_TABLES,'capa_r6_manual_decision_receipts')
