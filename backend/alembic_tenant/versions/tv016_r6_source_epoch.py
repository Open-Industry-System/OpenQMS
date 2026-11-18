"""R6 capture epoch without changing historical sources or R5 proofs."""
from alembic import op
import sqlalchemy as sa

revision = 'tv016_r6_source_epoch'
down_revision = 'tv015_r6_entry_contracts'
branch_labels = None
depends_on = None


def _schema():
    connection = op.get_bind()
    name = connection.scalar(sa.text('SELECT current_schema()'))
    return connection.dialect.identifier_preparer.quote_schema(name)


def upgrade():
    schema = _schema()
    connection = op.get_bind()
    if connection.scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM {schema}.fmea_documents WHERE lock_version IS NULL OR lock_version < 0)')):
        raise RuntimeError('Invalid FMEA source epoch; migration refused')
    op.add_column('capa_r6_source_origins', sa.Column('source_version_counter', sa.BigInteger(), nullable=True))
    op.create_check_constraint('ck_r6_source_version_counter', 'capa_r6_source_origins',
        "source_version_counter IS NULL OR (kind = 'fmea_projection' AND source_version_counter >= 0)")
    op.execute(f"""
CREATE FUNCTION {schema}.r6_fmea_source_epoch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.lock_version IS NULL OR NEW.lock_version IS NULL OR OLD.lock_version < 0 OR NEW.lock_version < OLD.lock_version THEN
    RAISE EXCEPTION 'FMEA source epoch cannot decrease' USING ERRCODE='23514';
  END IF;
  IF (NEW.graph_data IS DISTINCT FROM OLD.graph_data
      OR NEW.factory_id IS DISTINCT FROM OLD.factory_id
      OR NEW.product_line_code IS DISTINCT FROM OLD.product_line_code)
      AND NEW.lock_version = OLD.lock_version THEN
    NEW.lock_version := OLD.lock_version + 1;
  END IF;
  RETURN NEW;
END $$
""")
    op.execute(f'CREATE TRIGGER r6_fmea_source_epoch BEFORE UPDATE ON {schema}.fmea_documents FOR EACH ROW EXECUTE FUNCTION {schema}.r6_fmea_source_epoch()')


def downgrade():
    schema = _schema()
    if op.get_bind().scalar(sa.text(
            f'SELECT EXISTS (SELECT 1 FROM {schema}.capa_r6_source_origins) '
            f'OR EXISTS (SELECT 1 FROM {schema}.capa_r6_root_delivery_bindings)')):
        raise RuntimeError('R6 source evidence exists; downgrade refused')
    op.execute(f'DROP TRIGGER r6_fmea_source_epoch ON {schema}.fmea_documents')
    op.execute(f'DROP FUNCTION {schema}.r6_fmea_source_epoch()')
    op.drop_constraint('ck_r6_source_version_counter', 'capa_r6_source_origins', type_='check')
    op.drop_column('capa_r6_source_origins', 'source_version_counter')

