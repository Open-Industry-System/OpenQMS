"""Witness CAPA-owned snapshot-only local inputs without inventing external sources."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = '20261116_r6_local_snapshot'
down_revision = '20261116_r6_manual_receipts'
branch_labels = None
depends_on = None


def _schema():
    connection=op.get_bind()
    return connection.dialect.identifier_preparer.quote_schema(connection.scalar(sa.text('SELECT current_schema()')))


def upgrade():
    op.add_column('capa_r6_local_revisions',sa.Column('root_snapshot_revision_id',UUID(as_uuid=True),nullable=True))
    op.create_foreign_key('fk_r6_local_snapshot_root','capa_r6_local_revisions','capa_r6_root_revision_bodies',
        ['root_snapshot_revision_id','report_id'],['revision_id','report_id'],ondelete='RESTRICT')
    op.drop_constraint('ck_r6_local_inputs','capa_r6_local_revisions',type_='check')
    op.create_check_constraint('ck_r6_local_inputs','capa_r6_local_revisions',"source_count >= 0 AND jsonb_typeof(input_bindings)='object' AND octet_length(input_bindings::text)<=262144 AND jsonb_typeof(candidates)='array' AND octet_length(candidates::text)<=262144")
    op.create_check_constraint('ck_r6_local_snapshot_count','capa_r6_local_revisions',
        '(source_count=0) = (root_snapshot_revision_id IS NOT NULL)')
    schema=_schema()
    op.execute(f"""
CREATE FUNCTION {schema}.r6_validate_local_snapshot_witness() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE root RECORD; report RECORD; n bigint; valid_n bigint; ids jsonb; digest_value text;
BEGIN
  IF NEW.source_count <> 0 THEN RETURN NULL; END IF;
  SELECT * INTO report FROM {schema}.capa_eightd WHERE report_id=NEW.report_id;
  SELECT b.*,r.revision_no INTO root FROM {schema}.capa_r6_root_revision_bodies b
    JOIN {schema}.capa_d4_root_cause_revisions r ON r.revision_id=b.revision_id AND r.report_id=b.report_id
    WHERE b.revision_id=NEW.root_snapshot_revision_id AND b.report_id=NEW.report_id;
  IF root IS NULL OR report IS NULL OR root.binding_state <> 'controlled' OR root.source_count<=0
    OR NEW.input_bindings->>'root_revision_id' IS DISTINCT FROM NEW.root_snapshot_revision_id::text
    OR NEW.root_snapshot_revision_id IS DISTINCT FROM (SELECT revision_id FROM {schema}.capa_d4_root_cause_revisions
       WHERE report_id=NEW.report_id ORDER BY revision_no DESC LIMIT 1)
    OR NEW.candidates IS DISTINCT FROM '[]'::jsonb THEN
    RAISE EXCEPTION 'R6 local snapshot witness invalid' USING ERRCODE='23514';
  END IF;
  SELECT count(*),count(*) FILTER (WHERE o.kind='report_snapshot' AND o.module='capa'
      AND o.object_id=NEW.report_id AND o.report_id=NEW.report_id AND s.report_id=NEW.report_id
      AND o.factory_id=report.factory_id AND o.product_line_code=report.product_line_code
      AND o.fmea_id IS NULL AND o.node_id IS NULL
      AND ((s.kind='d2' AND o.projection_id='capa.d2.snapshot.v1') OR (s.kind='d3' AND o.projection_id='capa.d3.snapshot.v1'))
      AND o.version=s.version::text),
      to_jsonb(array_agg(rs.source_id::text ORDER BY rs.source_id::text)),
      encode(public.digest('['||string_agg(to_json(rs.source_id::text)::text,',' ORDER BY rs.source_id::text)||']','sha256'),'hex')
    INTO n,valid_n,ids,digest_value
    FROM {schema}.capa_r6_root_revision_sources rs
    LEFT JOIN {schema}.capa_r6_source_origins o ON o.source_id=rs.source_id AND o.report_id=rs.report_id
    LEFT JOIN {schema}.capa_r6_report_snapshots s ON s.snapshot_id=o.snapshot_id AND s.report_id=o.report_id
    WHERE rs.revision_id=NEW.root_snapshot_revision_id AND rs.report_id=NEW.report_id;
  IF n IS DISTINCT FROM root.source_count OR valid_n IS DISTINCT FROM n OR n=0
    OR digest_value IS DISTINCT FROM root.origin_digest OR NEW.input_bindings->'root_origin_ids' IS DISTINCT FROM ids THEN
    RAISE EXCEPTION 'R6 local snapshot origins incomplete' USING ERRCODE='23514';
  END IF;
  IF EXISTS (SELECT 1 FROM {schema}.capa_d5_measures m JOIN {schema}.capa_d5_proposals p ON p.proposal_id=m.proposal_id
       JOIN {schema}.capa_d5_proposal_sources ps ON ps.proposal_id=p.proposal_id WHERE p.report_id=NEW.report_id)
    OR EXISTS (SELECT 1 FROM {schema}.capa_d5_measures m JOIN {schema}.capa_d5_proposals p ON p.proposal_id=m.proposal_id
       JOIN {schema}.capa_r6_root_revision_sources rs ON rs.revision_id=p.revision_id AND rs.report_id=p.report_id
       JOIN {schema}.capa_r6_source_origins o ON o.source_id=rs.source_id AND o.report_id=rs.report_id
       WHERE p.report_id=NEW.report_id AND o.kind<>'report_snapshot')
    OR EXISTS (SELECT 1 FROM {schema}.capa_root_cause_verification v WHERE v.capa_id=NEW.report_id AND
       ((v.source_ref IS NOT NULL AND v.source_ref<>'null'::jsonb)
        OR (v.r6_source_origins IS NOT NULL AND v.r6_source_origins<>'null'::jsonb AND v.r6_source_origins<>'[]'::jsonb)))
    OR EXISTS (SELECT 1 FROM {schema}.capa_r6_local_sources WHERE report_id=NEW.report_id)
    OR (NEW.kind='manual_analysis' AND (EXISTS (SELECT 1 FROM {schema}.fmea_documents WHERE factory_id=report.factory_id AND product_line_code=report.product_line_code)
       OR EXISTS (SELECT 1 FROM {schema}.control_plans WHERE factory_id=report.factory_id AND product_line_code=report.product_line_code))) THEN
    RAISE EXCEPTION 'R6 local snapshot omitted external inputs' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$
""")
    # INSERT only: a later legitimate Root revision never rewrites or invalidates
    # the immutable witness retained by an older local business record.
    op.execute(f'CREATE CONSTRAINT TRIGGER r6_validate_local_snapshot_witness AFTER INSERT ON {schema}.capa_r6_local_revisions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {schema}.r6_validate_local_snapshot_witness()')


def downgrade():
    schema=_schema()
    if op.get_bind().scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {schema}.capa_r6_local_revisions WHERE root_snapshot_revision_id IS NOT NULL)')):
        raise RuntimeError('R6 local snapshot witnesses exist; downgrade refused')
    op.execute(f'DROP TRIGGER r6_validate_local_snapshot_witness ON {schema}.capa_r6_local_revisions')
    op.execute(f'DROP FUNCTION {schema}.r6_validate_local_snapshot_witness()')
    op.drop_constraint('ck_r6_local_snapshot_count','capa_r6_local_revisions',type_='check')
    op.drop_constraint('fk_r6_local_snapshot_root','capa_r6_local_revisions',type_='foreignkey')
    op.drop_column('capa_r6_local_revisions','root_snapshot_revision_id')
    op.drop_constraint('ck_r6_local_inputs','capa_r6_local_revisions',type_='check')
    op.create_check_constraint('ck_r6_local_inputs','capa_r6_local_revisions',"source_count > 0 AND jsonb_typeof(input_bindings)='object' AND octet_length(input_bindings::text)<=262144 AND jsonb_typeof(candidates)='array' AND octet_length(candidates::text)<=262144")
