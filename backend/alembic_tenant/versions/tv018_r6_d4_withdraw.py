"""Retain restricted D4 withdrawal reasons without ordinary audit bodies."""
from alembic import op
import sqlalchemy as sa
revision = 'tv018_r6_d4_withdraw'
down_revision = 'tv017_r6_d4_inputs'
branch_labels = None
depends_on = None


def _schema():
    connection=op.get_bind()
    return connection.dialect.identifier_preparer.quote_schema(connection.scalar(sa.text('SELECT current_schema()')))


def upgrade():
    op.execute('\nCREATE TABLE capa_d4_candidate_withdrawals (\n\treceipt_id UUID NOT NULL, \n\tcandidate_id UUID NOT NULL, \n\treport_id UUID NOT NULL, \n\treason TEXT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (receipt_id), \n\tFOREIGN KEY(candidate_id, report_id) REFERENCES capa_d4_candidates (candidate_id, report_id) ON DELETE RESTRICT, \n\tCONSTRAINT ck_d4_withdraw_reason CHECK (octet_length(reason) <= 16384 AND length(btrim(reason)) > 0), \n\tFOREIGN KEY(receipt_id) REFERENCES capa_r6_staff_receipts (receipt_id) ON DELETE RESTRICT\n)\n\n')
    schema=_schema()
    op.execute(f'CREATE TRIGGER r6_immutable_history BEFORE UPDATE OR DELETE ON {schema}.capa_d4_candidate_withdrawals FOR EACH ROW EXECUTE FUNCTION {schema}.r6_immutable_history()')
    op.execute(f"""
CREATE FUNCTION {schema}.r6_validate_d4_withdrawal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM {schema}.capa_r6_staff_receipts r
      WHERE r.receipt_id=NEW.receipt_id AND r.operation='d4_withdraw'
      AND r.candidate_id=NEW.candidate_id AND r.report_id=NEW.report_id
      AND r.root_revision_id IS NULL AND r.measure_revision_id IS NULL) THEN
    RAISE EXCEPTION 'R6 D4 withdrawal receipt mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
""")
    op.execute(f'CREATE TRIGGER r6_validate_d4_withdrawal BEFORE INSERT ON {schema}.capa_d4_candidate_withdrawals FOR EACH ROW EXECUTE FUNCTION {schema}.r6_validate_d4_withdrawal()')


def downgrade():
    schema=_schema()
    if op.get_bind().scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {schema}.capa_d4_candidate_withdrawals)')):
        raise RuntimeError('R6 D4 withdrawal evidence exists; downgrade refused')
    op.drop_table('capa_d4_candidate_withdrawals')
    op.execute(f'DROP FUNCTION {schema}.r6_validate_d4_withdrawal()')
