"""Retain actual CAPA sources for manual closure without new deletion pins."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = 'tv024_r6_local_capa_sources'
down_revision = 'tv023_r6_legacy_capture'
branch_labels = None
depends_on = None


def upgrade():
    # No FK/cascade/SET NULL to a source CAPA: deletion retains immutable
    # evidence and makes current authority unavailable, rather than pinning it.
    op.add_column('capa_r6_local_sources',sa.Column('source_capa_id',UUID(as_uuid=True),nullable=True))
    op.add_column('capa_r6_local_sources',sa.Column('source_capa_created_at',sa.DateTime(timezone=True),nullable=True))
    op.drop_constraint('ck_r6_local_source','capa_r6_local_sources',type_='check')
    op.create_check_constraint('ck_r6_local_source','capa_r6_local_sources',"module IN ('fmea','planning','capa') AND length(btrim(product_line_code))>0")
    op.create_check_constraint('ck_r6_local_capa_identity','capa_r6_local_sources',
        "(module='capa' AND source_capa_id IS NOT NULL AND source_capa_created_at IS NOT NULL AND object_id=source_capa_id) OR (module IN ('fmea','planning') AND source_capa_id IS NULL AND source_capa_created_at IS NULL)")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM capa_r6_local_sources WHERE module='capa' OR source_capa_id IS NOT NULL OR source_capa_created_at IS NOT NULL)")):
        raise RuntimeError('R6 CAPA source evidence must be retained')
    op.drop_constraint('ck_r6_local_capa_identity','capa_r6_local_sources',type_='check')
    op.drop_constraint('ck_r6_local_source','capa_r6_local_sources',type_='check')
    op.create_check_constraint('ck_r6_local_source','capa_r6_local_sources',"module IN ('fmea','planning') AND length(btrim(product_line_code))>0")
    op.drop_column('capa_r6_local_sources','source_capa_created_at')
    op.drop_column('capa_r6_local_sources','source_capa_id')
