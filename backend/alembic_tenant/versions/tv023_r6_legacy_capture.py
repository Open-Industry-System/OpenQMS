"""Immutable server-bound pre-fusion legacy recommendation captures; no backfill."""
from alembic import op
import sqlalchemy as sa
revision = 'tv023_r6_legacy_capture'
down_revision = 'tv022_r6_local_snapshot'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE capa_r6_legacy_captures (
 capture_id UUID PRIMARY KEY,
 report_id UUID NOT NULL REFERENCES capa_eightd(report_id) ON DELETE RESTRICT,
 actor_id UUID NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
 namespace VARCHAR(64) NOT NULL,
 tenant_id UUID,
 tenant_generation BIGINT NOT NULL,
 stage VARCHAR(2) NOT NULL,
 text_digest VARCHAR(64) NOT NULL,
 target_material VARCHAR(128) NOT NULL,
 source_bindings JSONB NOT NULL,
 binding_hmac VARCHAR(64) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT ck_r6_legacy_namespace CHECK ((namespace='single:public' AND tenant_id IS NULL AND tenant_generation=0) OR (namespace ~ '^tenant_' AND tenant_id IS NOT NULL AND tenant_generation>=0)),
 CONSTRAINT ck_r6_legacy_stage CHECK (stage IN ('d4','d5')),
 CONSTRAINT ck_r6_legacy_digest CHECK (text_digest ~ '^[0-9a-f]{64}$' AND binding_hmac ~ '^[0-9a-f]{64}$'),
 CONSTRAINT ck_r6_legacy_material CHECK (length(target_material)>0),
 CONSTRAINT ck_r6_legacy_sources CHECK (jsonb_typeof(source_bindings)='array' AND jsonb_array_length(source_bindings)<=1000 AND octet_length(source_bindings::text)<=262144)
)
""")
    schema=op.get_bind().dialect.identifier_preparer.quote_schema(op.get_bind().scalar(sa.text('SELECT current_schema()')))
    op.execute(f"""CREATE FUNCTION {schema}.r6_reject_legacy_capture_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'R6 legacy capture is immutable' USING ERRCODE='23514'; END; $$""")
    op.execute(f'CREATE TRIGGER r6_legacy_capture_immutable BEFORE UPDATE OR DELETE ON {schema}.capa_r6_legacy_captures FOR EACH ROW EXECUTE FUNCTION {schema}.r6_reject_legacy_capture_mutation()')


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM capa_r6_legacy_captures)')):
        raise RuntimeError('R6 legacy capture data must be retained')
    op.drop_table('capa_r6_legacy_captures')
    op.execute('DROP FUNCTION r6_reject_legacy_capture_mutation()')
