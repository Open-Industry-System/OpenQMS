"""Independent empty-root D4 input delivery; no Root/P facts are invented."""
from alembic import op
import sqlalchemy as sa

revision = 'tv017_r6_d4_inputs'
down_revision = 'tv016_r6_source_epoch'
branch_labels = None
depends_on = None
TABLES = ('agent_d4_input_receipts', 'agent_d4_input_receipt_sources', 'agent_d4_command_inputs')


def _schema():
    connection = op.get_bind()
    return connection.dialect.identifier_preparer.quote_schema(connection.scalar(sa.text('SELECT current_schema()')))


def upgrade():
    op.execute("\nCREATE TABLE agent_d4_input_receipts (\n\treceipt_id UUID NOT NULL, \n\treport_id UUID NOT NULL, \n\ttask_id UUID NOT NULL, \n\trun_id UUID NOT NULL, \n\texecutor_id UUID NOT NULL, \n\tinstallation_id UUID NOT NULL, \n\tdeployment_id UUID NOT NULL, \n\tlease_epoch BIGINT NOT NULL, \n\ttenant_generation BIGINT NOT NULL, \n\tdeployment_config_hmac VARCHAR(64) NOT NULL, \n\tsource_count INTEGER NOT NULL, \n\tinput_versions JSONB NOT NULL, \n\treceipt_hmac VARCHAR(64) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (receipt_id), \n\tFOREIGN KEY(task_id, report_id) REFERENCES agent_tasks (task_id, target_capa_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(run_id, task_id) REFERENCES agent_runs (run_id, task_id) ON DELETE RESTRICT, \n\tCONSTRAINT uq_d4_input_report UNIQUE (receipt_id, report_id), \n\tCONSTRAINT uq_d4_input_target UNIQUE (receipt_id, report_id, task_id, run_id), \n\tCONSTRAINT ck_d4_input_counts CHECK (lease_epoch >= 0 AND tenant_generation >= 0 AND source_count BETWEEN 3 AND 64), \n\tCONSTRAINT ck_d4_input_hmac CHECK (deployment_config_hmac ~ '^[0-9a-f]{64}$' AND receipt_hmac ~ '^[0-9a-f]{64}$' AND jsonb_typeof(input_versions) = 'object'), \n\tFOREIGN KEY(executor_id) REFERENCES users (user_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(installation_id) REFERENCES agent_plugin_installations (installation_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(deployment_id) REFERENCES agent_model_deployments (deployment_id) ON DELETE RESTRICT\n)\n\n")
    op.execute('\nCREATE TABLE agent_d4_input_receipt_sources (\n\treceipt_id UUID NOT NULL, \n\treport_id UUID NOT NULL, \n\tsource_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (receipt_id, source_id), \n\tFOREIGN KEY(receipt_id, report_id) REFERENCES agent_d4_input_receipts (receipt_id, report_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(source_id, report_id) REFERENCES capa_r6_source_origins (source_id, report_id) ON DELETE RESTRICT\n)\n\n')
    op.execute('\nCREATE TABLE agent_d4_command_inputs (\n\tcommand_id UUID NOT NULL, \n\treceipt_id UUID NOT NULL, \n\treport_id UUID NOT NULL, \n\ttask_id UUID NOT NULL, \n\trun_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (command_id, receipt_id), \n\tFOREIGN KEY(command_id, report_id, task_id, run_id) REFERENCES agent_d4_candidate_commands (command_id, report_id, task_id, run_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(receipt_id, report_id, task_id, run_id) REFERENCES agent_d4_input_receipts (receipt_id, report_id, task_id, run_id) ON DELETE RESTRICT\n)\n\n')
    schema = _schema()
    for table in TABLES:
        op.execute(f'CREATE TRIGGER r6_immutable_history BEFORE UPDATE OR DELETE ON {schema}.{table} FOR EACH ROW EXECUTE FUNCTION {schema}.r6_immutable_history()')
    op.execute(f"""
CREATE FUNCTION {schema}.r6_complete_d4_inputs() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r uuid; expected integer; actual bigint; versions jsonb; linked uuid[];
BEGIN
  r := NEW.receipt_id;
  SELECT source_count,input_versions INTO expected,versions FROM {schema}.agent_d4_input_receipts WHERE receipt_id=r;
  SELECT count(*),array_agg(source_id) INTO actual,linked FROM {schema}.agent_d4_input_receipt_sources WHERE receipt_id=r;
  IF expected IS NULL OR expected <> actual OR actual <> (SELECT count(*) FROM jsonb_object_keys(versions))
      OR EXISTS (SELECT 1 FROM unnest(linked) s WHERE NOT versions ? s::text) THEN
    RAISE EXCEPTION 'R6 D4 input sources incomplete' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$
""")
    for table in ('agent_d4_input_receipts', 'agent_d4_input_receipt_sources'):
        op.execute(f'CREATE CONSTRAINT TRIGGER r6_complete_d4_inputs AFTER INSERT ON {schema}.{table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {schema}.r6_complete_d4_inputs()')


def downgrade():
    schema = _schema()
    if op.get_bind().scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {schema}.agent_d4_input_receipts)')):
        raise RuntimeError('R6 D4 input evidence exists; downgrade refused')
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute(f'DROP FUNCTION {schema}.r6_complete_d4_inputs()')
