"""Immutable business DDL baseline; no dynamic model metadata or dump at runtime."""
from alembic import op

from alembic_tenant.snapshot.business_20260927 import DDL
from app.services.tenant_schema_diff import load_snapshot_manifest, verify_snapshot_checksum

revision = "tv001_business_snapshot"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    verify_snapshot_checksum(load_snapshot_manifest())
    for statement in DDL:
        op.execute(statement)


def downgrade():
    raise RuntimeError("Tenant baseline is irreversible; no schema drop via Alembic")
