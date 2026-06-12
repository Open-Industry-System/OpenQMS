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