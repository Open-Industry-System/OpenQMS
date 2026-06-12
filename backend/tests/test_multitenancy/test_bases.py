import pytest
from app.database import PlatformBase, TenantBase


def test_platform_base_is_separate_from_tenant_base():
    """PlatformBase and TenantBase must be independent DeclarativeBases."""
    assert PlatformBase is not TenantBase
    assert PlatformBase.metadata is not TenantBase.metadata


def test_tenant_base_has_existing_business_models():
    """After models are imported, TenantBase should contain business tables."""
    import app.models  # noqa: F401
    assert "users" in TenantBase.metadata.tables
    assert "factories" in TenantBase.metadata.tables
    assert "fmea_documents" in TenantBase.metadata.tables


def test_platform_base_only_has_platform_models():
    """After platform models are registered, PlatformBase should only have platform tables."""
    import app.models  # noqa: F401
    from app.models.tenant import Tenant  # noqa: F401
    from app.models.platform_admin import PlatformAdminUser  # noqa: F401
    from app.models.reference_template import ReferenceTemplate  # noqa: F401

    platform_tables = set(PlatformBase.metadata.tables.keys())
    expected = {"tenants", "tenant_migrations", "platform_admin_users", "reference_templates"}
    assert expected.issubset(platform_tables)
    assert "users" not in platform_tables
    assert "fmea_documents" not in platform_tables


# --- Platform model field and inheritance tests ---

from app.models.tenant import Tenant
from app.models.platform_admin import PlatformAdminUser
from app.models.reference_template import ReferenceTemplate
from app.models.tenant_migration import TenantMigration


def test_tenant_model_fields():
    columns = {c.name for c in Tenant.__table__.columns}
    required = {"id", "name", "slug", "schema_name", "subdomain", "plan", "status",
                "provisioning_step", "provisioning_error", "db_instance", "db_size_bytes",
                "user_count", "last_active_at", "created_at", "updated_at"}
    assert required.issubset(columns)


def test_tenant_model_uses_platform_base():
    assert issubclass(Tenant, PlatformBase)
    assert Tenant.__tablename__ == "tenants"


def test_tenant_slug_check_constraint():
    constraints = [c for c in Tenant.__table__.constraints
                   if hasattr(c, 'sqltext') and 'slug' in str(c.sqltext)]
    assert len(constraints) >= 1


def test_tenant_schema_name_check_constraint():
    constraints = [c for c in Tenant.__table__.constraints
                   if hasattr(c, 'sqltext') and 'schema_name' in str(c.sqltext)]
    assert len(constraints) >= 1


def test_platform_admin_model():
    assert issubclass(PlatformAdminUser, PlatformBase)
    columns = {c.name for c in PlatformAdminUser.__table__.columns}
    required = {"id", "email", "password_hash", "role", "is_active", "created_at", "updated_at"}
    assert required.issubset(columns)


def test_reference_template_model():
    assert issubclass(ReferenceTemplate, PlatformBase)
    columns = {c.name for c in ReferenceTemplate.__table__.columns}
    required = {"id", "category", "name", "description", "content", "version", "created_at", "updated_at"}
    assert required.issubset(columns)


def test_tenant_migration_model():
    assert issubclass(TenantMigration, PlatformBase)
    columns = {c.name for c in TenantMigration.__table__.columns}
    required = {"id", "tenant_id", "version", "status", "started_at", "completed_at",
                "applied_at", "error_message", "created_at", "updated_at"}
    assert required.issubset(columns)