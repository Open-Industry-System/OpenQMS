"""Retain known verification source restrictions through editable source_ref."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '20261116_r6_verify_origins'
down_revision = '20261116_r6_d4_withdraw'
branch_labels = None
depends_on = None


def _schema():
    connection = op.get_bind()
    return connection.dialect.identifier_preparer.quote_schema(connection.scalar(sa.text('SELECT current_schema()')))


def upgrade():
    op.add_column('capa_root_cause_verification', sa.Column('r6_source_origins', JSONB(), nullable=True))
    schema = _schema()
    op.execute(f"""
CREATE FUNCTION {schema}.r6_verification_ref_origin(ref jsonb) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE fid uuid; scope_factory uuid; scope_line text;
BEGIN
  IF ref IS NULL OR ref = 'null'::jsonb THEN RETURN NULL; END IF;
  IF jsonb_typeof(ref) <> 'object' THEN RAISE EXCEPTION 'R6 verification source invalid' USING ERRCODE='23514'; END IF;
  IF (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(ref) k) IS DISTINCT FROM ARRAY['cause_node_id','fmea_id']
      OR jsonb_typeof(ref->'fmea_id') <> 'string' OR jsonb_typeof(ref->'cause_node_id') <> 'string'
      OR (ref->>'fmea_id') !~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
      OR length(btrim(ref->>'cause_node_id')) = 0 OR length(ref->>'cause_node_id') > 128 THEN
    RAISE EXCEPTION 'R6 verification source invalid' USING ERRCODE='23514';
  END IF;
  fid := (ref->>'fmea_id')::uuid;
  SELECT factory_id,product_line_code INTO scope_factory,scope_line FROM {schema}.fmea_documents WHERE fmea_id=fid FOR SHARE;
  IF NOT FOUND OR scope_factory IS NULL OR scope_line IS NULL OR length(btrim(scope_line))=0 THEN
    RAISE EXCEPTION 'R6 verification source unavailable' USING ERRCODE='23514';
  END IF;
  RETURN jsonb_build_object('kind','fmea','fmea_id',fid::text,'cause_node_id',ref->>'cause_node_id',
      'factory_id',scope_factory::text,'product_line_code',scope_line);
END $$;
""")
    op.execute(f"""
CREATE FUNCTION {schema}.r6_retain_verification_origins() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE origins jsonb; origin jsonb; captured jsonb;
BEGIN
  IF TG_OP='UPDATE' THEN
    IF NEW.verification_id IS DISTINCT FROM OLD.verification_id OR NEW.capa_id IS DISTINCT FROM OLD.capa_id
        OR NEW.factory_id IS DISTINCT FROM OLD.factory_id THEN
      RAISE EXCEPTION 'R6 verification identity immutable' USING ERRCODE='23514';
    END IF;
    IF OLD.r6_source_origins IS NOT NULL AND OLD.r6_source_origins <> 'null'::jsonb
        AND (NEW.r6_source_origins IS NULL OR NEW.r6_source_origins='null'::jsonb
          OR NOT NEW.r6_source_origins @> OLD.r6_source_origins) THEN
      RAISE EXCEPTION 'R6 verification restrictions cannot shrink' USING ERRCODE='23514';
    END IF;
  END IF;
  origins := CASE WHEN NEW.r6_source_origins IS NULL OR NEW.r6_source_origins='null'::jsonb THEN '[]'::jsonb ELSE NEW.r6_source_origins END;
  IF jsonb_typeof(origins) <> 'array' OR jsonb_array_length(origins)>200 THEN
    RAISE EXCEPTION 'R6 verification origins invalid' USING ERRCODE='23514';
  END IF;
  FOR origin IN SELECT value FROM jsonb_array_elements(origins) LOOP
    IF jsonb_typeof(origin) <> 'object' THEN RAISE EXCEPTION 'R6 verification origin invalid' USING ERRCODE='23514'; END IF;
    IF (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(origin) k)
          IS DISTINCT FROM ARRAY['cause_node_id','factory_id','fmea_id','kind','product_line_code']
        OR origin->>'kind' <> 'fmea' OR jsonb_typeof(origin->'kind') <> 'string'
        OR jsonb_typeof(origin->'fmea_id') <> 'string' OR jsonb_typeof(origin->'factory_id') <> 'string'
        OR (origin->>'fmea_id') !~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
        OR (origin->>'factory_id') !~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
        OR jsonb_typeof(origin->'cause_node_id') <> 'string' OR length(btrim(origin->>'cause_node_id'))=0
        OR length(origin->>'cause_node_id')>128 OR jsonb_typeof(origin->'product_line_code') <> 'string'
        OR length(btrim(origin->>'product_line_code'))=0 OR length(origin->>'product_line_code')>20 THEN
      RAISE EXCEPTION 'R6 verification origin invalid' USING ERRCODE='23514';
    END IF;
    IF TG_OP='INSERT' OR OLD.r6_source_origins IS NULL OR NOT OLD.r6_source_origins @> jsonb_build_array(origin) THEN
      captured := {schema}.r6_verification_ref_origin(jsonb_build_object('fmea_id',origin->>'fmea_id','cause_node_id',origin->>'cause_node_id'));
      IF captured IS DISTINCT FROM origin THEN RAISE EXCEPTION 'R6 verification origin scope invalid' USING ERRCODE='23514'; END IF;
    END IF;
  END LOOP;
  IF TG_OP='UPDATE' THEN
    captured := {schema}.r6_verification_ref_origin(OLD.source_ref);
    IF captured IS NOT NULL AND NOT origins @> jsonb_build_array(captured) THEN origins:=origins||jsonb_build_array(captured); END IF;
  END IF;
  captured := {schema}.r6_verification_ref_origin(NEW.source_ref);
  IF captured IS NOT NULL AND NOT origins @> jsonb_build_array(captured) THEN origins:=origins||jsonb_build_array(captured); END IF;
  IF jsonb_array_length(origins) <> (SELECT count(DISTINCT (v->>'fmea_id',v->>'cause_node_id')) FROM jsonb_array_elements(origins) v)
      OR jsonb_array_length(origins)>200 THEN
    RAISE EXCEPTION 'R6 verification duplicate origins' USING ERRCODE='23514';
  END IF;
  SELECT coalesce(jsonb_agg(v ORDER BY v->>'fmea_id',v->>'cause_node_id'),'[]'::jsonb) INTO origins FROM jsonb_array_elements(origins) v;
  NEW.r6_source_origins:=origins;
  RETURN NEW;
END $$;
""")
    op.execute(f"""
CREATE TRIGGER r6_retain_verification_origins BEFORE INSERT OR UPDATE ON {schema}.capa_root_cause_verification
FOR EACH ROW EXECUTE FUNCTION {schema}.r6_retain_verification_origins();
""")


def downgrade():
    schema = _schema()
    if op.get_bind().scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {schema}.capa_root_cause_verification WHERE r6_source_origins IS NOT NULL)')):
        raise RuntimeError('R6 verification source restrictions exist; downgrade refused')
    op.execute(f'DROP TRIGGER r6_retain_verification_origins ON {schema}.capa_root_cause_verification')
    op.execute(f'DROP FUNCTION {schema}.r6_retain_verification_origins()')
    op.execute(f'DROP FUNCTION {schema}.r6_verification_ref_origin(jsonb)')
    op.drop_column('capa_root_cause_verification', 'r6_source_origins')
