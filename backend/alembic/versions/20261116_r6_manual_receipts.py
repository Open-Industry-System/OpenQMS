"""Durable exact manual gate decision receipts; no model wire changes."""
from alembic import op
import sqlalchemy as sa
revision = '20261116_r6_manual_receipts'
down_revision = '20261116_r6_local_closure'
branch_labels = None
depends_on = None


def _schema():
    connection=op.get_bind()
    return connection.dialect.identifier_preparer.quote_schema(connection.scalar(sa.text('SELECT current_schema()')))


def upgrade():
    op.execute("\nCREATE TABLE capa_r6_manual_decision_receipts (\n\treceipt_id UUID NOT NULL, \n\tactor_id UUID NOT NULL, \n\treport_id UUID NOT NULL, \n\tanalysis_id UUID NOT NULL, \n\tdecision_id UUID NOT NULL, \n\toperation VARCHAR(16) NOT NULL, \n\toperation_key VARCHAR(128) NOT NULL, \n\trequest_hmac VARCHAR(64) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (receipt_id), \n\tCONSTRAINT uq_r6_manual_decision_key UNIQUE (actor_id, operation_key), \n\tCONSTRAINT uq_r6_manual_decision_result UNIQUE (decision_id), \n\tCONSTRAINT ck_r6_manual_decision_operation CHECK (operation IN ('audit','defer','no_affected','waiver')), \n\tCONSTRAINT ck_r6_manual_decision_receipt CHECK (operation_key ~ '^[A-Za-z0-9._:-]{1,128}$' AND request_hmac ~ '^[0-9a-f]{64}$'), \n\tFOREIGN KEY(actor_id) REFERENCES users (user_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(report_id) REFERENCES capa_eightd (report_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(analysis_id) REFERENCES capa_docg_analysis (analysis_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(decision_id) REFERENCES capa_docg_decision (decision_id) ON DELETE RESTRICT\n)\n\n")
    schema=_schema()
    op.execute(f'CREATE TRIGGER r6_immutable_history BEFORE UPDATE OR DELETE ON {schema}.capa_r6_manual_decision_receipts FOR EACH ROW EXECUTE FUNCTION {schema}.r6_immutable_history()')
    op.execute(f"""
CREATE FUNCTION {schema}.r6_validate_manual_decision_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a RECORD; d RECORD;
BEGIN
  SELECT * INTO a FROM {schema}.capa_docg_analysis WHERE analysis_id=NEW.analysis_id;
  SELECT * INTO d FROM {schema}.capa_docg_decision WHERE decision_id=NEW.decision_id;
  IF a IS NULL OR d IS NULL OR a.analysis_method <> 'manual' OR a.status <> 'done'
     OR a.capa_id <> NEW.report_id OR d.analysis_id <> NEW.analysis_id OR d.factory_id <> a.factory_id
     OR d.decided_by <> NEW.actor_id THEN
    RAISE EXCEPTION 'R6 manual decision receipt mismatch' USING ERRCODE='23514';
  END IF;
  IF (NEW.operation='audit' AND (d.audit_run_id IS NULL OR d.no_affected_confirmed OR d.waiver_reason IS NOT NULL OR NOT EXISTS (SELECT 1 FROM {schema}.capa_docg_audit x WHERE x.analysis_id=a.analysis_id AND x.audit_run_id=d.audit_run_id)))
     OR (NEW.operation='no_affected' AND (d.decision <> 'passed' OR NOT d.no_affected_confirmed OR d.audit_run_id IS NOT NULL OR d.waiver_reason IS NOT NULL))
     OR (NEW.operation='defer' AND (d.decision <> 'deferred' OR d.defer_reason IS NULL OR d.defer_owner IS NULL OR d.defer_deadline IS NULL))
     OR (NEW.operation='waiver' AND (d.decision <> 'passed' OR d.no_affected_confirmed OR d.waiver_reason IS NULL OR d.waiver_items IS NULL OR jsonb_typeof(d.waiver_items)<>'array' OR jsonb_array_length(d.waiver_items)=0 OR d.audit_run_id IS NULL)) THEN
    RAISE EXCEPTION 'R6 manual decision receipt semantics invalid' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$
""")
    op.execute(f'CREATE CONSTRAINT TRIGGER r6_validate_manual_decision_receipt AFTER INSERT ON {schema}.capa_r6_manual_decision_receipts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {schema}.r6_validate_manual_decision_receipt()')


def downgrade():
    schema=_schema()
    if op.get_bind().scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {schema}.capa_r6_manual_decision_receipts)')):
        raise RuntimeError('R6 manual decision receipts exist; downgrade refused')
    op.drop_table('capa_r6_manual_decision_receipts')
    op.execute(f'DROP FUNCTION {schema}.r6_validate_manual_decision_receipt()')
