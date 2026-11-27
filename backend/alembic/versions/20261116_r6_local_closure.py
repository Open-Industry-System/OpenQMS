"""Controlled local prevention, manual analysis and explicit non-execution records."""
from alembic import op
import sqlalchemy as sa
revision = '20261116_r6_local_closure'
down_revision = '20261116_r6_verify_origins'
branch_labels = None
depends_on = None


def _schema():
    connection=op.get_bind()
    return connection.dialect.identifier_preparer.quote_schema(connection.scalar(sa.text('SELECT current_schema()')))


def upgrade():
    op.add_column('capa_docg_analysis',sa.Column('analysis_method',sa.String(10),nullable=False,server_default='model'))
    op.create_check_constraint('ck_docg_analysis_method','capa_docg_analysis',"analysis_method IN ('model','manual')")
    op.drop_constraint('chk_docg_analysis_done_complete','capa_docg_analysis',type_='check')
    op.create_check_constraint('chk_docg_analysis_done_complete','capa_docg_analysis',"status!='done' OR (affected_docs IS NOT NULL AND analysis_input_hash IS NOT NULL AND ((analysis_method='model' AND llm_available=true) OR (analysis_method='manual' AND llm_available=false)) AND completed_at IS NOT NULL)")
    op.execute('\nCREATE TABLE capa_r6_local_revisions (\n\trevision_id UUID NOT NULL, \n\treport_id UUID NOT NULL, \n\tkind VARCHAR(24) NOT NULL, \n\trevision_no BIGINT NOT NULL, \n\tpredecessor_id UUID, \n\tactor_id UUID NOT NULL, \n\tanalysis_id UUID, \n\toperation_key VARCHAR(128) NOT NULL, \n\trequest_hmac VARCHAR(64) NOT NULL, \n\ttext TEXT, \n\treason TEXT NOT NULL, \n\tbasis TEXT, \n\tinput_bindings JSONB NOT NULL, \n\tcandidates JSONB NOT NULL, \n\tchannels JSONB, \n\tsource_count INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (revision_id), \n\tFOREIGN KEY(predecessor_id, report_id, kind) REFERENCES capa_r6_local_revisions (revision_id, report_id, kind) ON DELETE RESTRICT, \n\tCONSTRAINT uq_r6_local_kind UNIQUE (revision_id, report_id, kind), \n\tCONSTRAINT uq_r6_local_report UNIQUE (revision_id, report_id), \n\tCONSTRAINT uq_r6_local_revision UNIQUE (report_id, kind, revision_no), \n\tCONSTRAINT uq_r6_local_successor UNIQUE (predecessor_id), \n\tCONSTRAINT uq_r6_local_operation UNIQUE (actor_id, operation_key), \n\tCONSTRAINT uq_r6_local_analysis UNIQUE (analysis_id), \n\tCONSTRAINT ck_r6_local_kind CHECK (kind IN (\'prevention\',\'manual_analysis\',\'propagation\')), \n\tCONSTRAINT ck_r6_local_predecessor CHECK (revision_no > 0 AND ((revision_no=1 AND predecessor_id IS NULL) OR (revision_no>1 AND predecessor_id IS NOT NULL))), \n\tCONSTRAINT ck_r6_local_receipt CHECK (operation_key ~ \'^[A-Za-z0-9._:-]{1,128}$\' AND request_hmac ~ \'^[0-9a-f]{64}$\'), \n\tCONSTRAINT ck_r6_local_analysis CHECK ((kind=\'manual_analysis\') = (analysis_id IS NOT NULL)), \n\tCONSTRAINT ck_r6_local_body CHECK ((kind=\'prevention\' AND text IS NOT NULL AND basis IS NOT NULL AND octet_length(text)<=16384 AND length(btrim(text))>0 AND octet_length(basis)<=16384 AND length(btrim(basis))>0) OR (kind<>\'prevention\' AND text IS NULL AND basis IS NULL)), \n\tCONSTRAINT ck_r6_local_channels CHECK ((kind=\'propagation\' AND channels IS NOT NULL AND channels = \'{"lessons":"NOT_EXECUTED","knowledge":"NOT_EXECUTED","lateral":"NOT_EXECUTED","supplier_risk":"NOT_EXECUTED"}\'::jsonb) OR (kind<>\'propagation\' AND channels IS NULL)), \n\tCONSTRAINT ck_r6_local_inputs CHECK (source_count > 0 AND jsonb_typeof(input_bindings)=\'object\' AND octet_length(input_bindings::text)<=262144 AND jsonb_typeof(candidates)=\'array\' AND octet_length(candidates::text)<=262144), \n\tCONSTRAINT ck_r6_local_reason CHECK (octet_length(reason) <= 16384 AND length(btrim(reason)) > 0), \n\tFOREIGN KEY(report_id) REFERENCES capa_eightd (report_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(actor_id) REFERENCES users (user_id) ON DELETE RESTRICT, \n\tFOREIGN KEY(analysis_id) REFERENCES capa_docg_analysis (analysis_id) ON DELETE RESTRICT\n)\n\n')
    op.execute("\nCREATE TABLE capa_r6_local_sources (\n\trevision_id UUID NOT NULL, \n\treport_id UUID NOT NULL, \n\tmodule VARCHAR(16) NOT NULL, \n\tobject_id UUID NOT NULL, \n\tfactory_id UUID NOT NULL, \n\tproduct_line_code VARCHAR(20) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (revision_id, module, object_id), \n\tFOREIGN KEY(revision_id, report_id) REFERENCES capa_r6_local_revisions (revision_id, report_id) ON DELETE RESTRICT, \n\tCONSTRAINT ck_r6_local_source CHECK (module IN ('fmea','planning') AND length(btrim(product_line_code))>0), \n\tFOREIGN KEY(factory_id) REFERENCES factories (id) ON DELETE RESTRICT\n)\n\n")
    schema=_schema()
    for table in ('capa_r6_local_revisions','capa_r6_local_sources'):
        op.execute(f'CREATE TRIGGER r6_immutable_history BEFORE UPDATE OR DELETE ON {schema}.{table} FOR EACH ROW EXECUTE FUNCTION {schema}.r6_immutable_history()')
    op.execute(f"""
CREATE FUNCTION {schema}.r6_complete_local_record() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE record_id uuid; parent RECORD; actual_count bigint;
BEGIN
  IF TG_TABLE_NAME='capa_docg_analysis' THEN
    IF NEW.analysis_method <> 'manual' THEN RETURN NULL; END IF;
    SELECT * INTO parent FROM {schema}.capa_r6_local_revisions WHERE analysis_id=NEW.analysis_id;
    IF NOT FOUND OR parent.report_id <> NEW.capa_id OR parent.kind <> 'manual_analysis' OR NEW.status <> 'done' THEN
      RAISE EXCEPTION 'R6 manual analysis record incomplete' USING ERRCODE='23514';
    END IF;
  ELSE
    SELECT * INTO parent FROM {schema}.capa_r6_local_revisions WHERE revision_id=NEW.revision_id;
  END IF;
  IF parent IS NULL THEN RETURN NULL; END IF;
  SELECT count(*) INTO actual_count FROM {schema}.capa_r6_local_sources WHERE revision_id=parent.revision_id AND report_id=parent.report_id;
  IF actual_count <> parent.source_count THEN RAISE EXCEPTION 'R6 local sources incomplete' USING ERRCODE='23514'; END IF;
  IF parent.predecessor_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {schema}.capa_r6_local_revisions p WHERE p.revision_id=parent.predecessor_id AND p.report_id=parent.report_id AND p.kind=parent.kind AND p.revision_no=parent.revision_no-1) THEN
    RAISE EXCEPTION 'R6 local predecessor invalid' USING ERRCODE='23514';
  END IF;
  IF parent.kind='manual_analysis' AND NOT EXISTS (SELECT 1 FROM {schema}.capa_docg_analysis a JOIN {schema}.capa_eightd c ON c.report_id=a.capa_id WHERE a.analysis_id=parent.analysis_id AND a.capa_id=parent.report_id AND a.factory_id=c.factory_id AND a.analysis_method='manual' AND a.status='done' AND a.llm_available=false) THEN
    RAISE EXCEPTION 'R6 local analysis mismatch' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$
""")
    for table in ('capa_r6_local_revisions','capa_r6_local_sources','capa_docg_analysis'):
        op.execute(f'CREATE CONSTRAINT TRIGGER r6_complete_local_record AFTER INSERT OR UPDATE ON {schema}.{table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {schema}.r6_complete_local_record()')


def downgrade():
    schema=_schema()
    if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {schema}.capa_r6_local_revisions) OR EXISTS (SELECT 1 FROM {schema}.capa_docg_analysis WHERE analysis_method='manual')")):
        raise RuntimeError('R6 local closure evidence exists; downgrade refused')
    op.execute(f'DROP TRIGGER r6_complete_local_record ON {schema}.capa_docg_analysis')
    op.drop_table('capa_r6_local_sources')
    op.drop_table('capa_r6_local_revisions')
    op.execute(f'DROP FUNCTION {schema}.r6_complete_local_record()')
    op.drop_constraint('chk_docg_analysis_done_complete','capa_docg_analysis',type_='check')
    op.create_check_constraint('chk_docg_analysis_done_complete','capa_docg_analysis',"status!='done' OR (affected_docs IS NOT NULL AND analysis_input_hash IS NOT NULL AND llm_available=true AND completed_at IS NOT NULL)")
    op.drop_constraint('ck_docg_analysis_method','capa_docg_analysis',type_='check')
    op.drop_column('capa_docg_analysis','analysis_method')
