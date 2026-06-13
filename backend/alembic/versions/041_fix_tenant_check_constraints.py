"""fix tenant check constraints — regex patterns had triple-quoted literals

The original p001_platform_tables migration created check constraints with
Python string literals that PostgreSQL stored with extra quote characters,
making the regex patterns always fail. This migration drops and recreates
all three tenant check constraints with correct single-quoted patterns.

Revision ID: 041
Revises: 040_add_unique_constraints
"""
from alembic import op


revision = '041'
down_revision = '040'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenants_schema_name_format")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenants_slug_format")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenants_subdomain_format")

    op.execute("ALTER TABLE tenants ADD CONSTRAINT ck_tenants_schema_name_format "
               "CHECK (schema_name ~ '^tenant_[a-z0-9_]{1,56}$')")
    op.execute("ALTER TABLE tenants ADD CONSTRAINT ck_tenants_slug_format "
               "CHECK (slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$')")
    op.execute("ALTER TABLE tenants ADD CONSTRAINT ck_tenants_subdomain_format "
               "CHECK (subdomain ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$')")


def downgrade() -> None:
    # Re-create the broken triple-quoted versions (matching original p001)
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenants_schema_name_format")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenants_slug_format")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenants_subdomain_format")

    op.execute("ALTER TABLE tenants ADD CONSTRAINT ck_tenants_schema_name_format "
               "CHECK (schema_name ~ '''^tenant_[a-z0-9_]{1,56}$''')")
    op.execute("ALTER TABLE tenants ADD CONSTRAINT ck_tenants_slug_format "
               "CHECK (slug ~ '''^[a-z0-9]([a-z0-9-]*[a-z0-9])?$''')")
    op.execute("ALTER TABLE tenants ADD CONSTRAINT ck_tenants_subdomain_format "
               "CHECK (subdomain ~ '''^[a-z0-9]([a-z0-9-]*[a-z0-9])?$''')")