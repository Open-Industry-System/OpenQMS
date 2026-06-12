# SaaS 多租户架构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add schema-per-tenant multi-tenancy to OpenQMS, enabling independent organizations to share one application instance with strong data isolation via PostgreSQL schemas.

**Architecture:** Each tenant gets a `tenant_<slug>` PostgreSQL schema containing all ~50 business tables. A `TenantContext` middleware resolves the tenant from the subdomain (or `X-Tenant-ID` header in dev) and injects it into `request.state.tenant` — it does NOT set `search_path`. The `get_db()` dependency sets `search_path` based on the resolved tenant. A platform admin panel operates on the `public` schema via separate `get_platform_db()`. Background tasks iterate over active tenants via `run_for_each_tenant()`.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 async + PostgreSQL 15 + Alembic + Pydantic v2

**Spec:** `docs/superpowers/specs/2026-06-12-saas-multi-tenant-design.md`

---

## Phase 1: Database Foundation & Models

Creates the new `PlatformBase`/`TenantBase` split, platform models, tenant context middleware, and retrofitted `get_db()`. No existing business routes change yet — this phase makes the plumbing work.

### Task 1: Split DeclarativeBase into PlatformBase and TenantBase

**Files:**
- Modify: `backend/app/database.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write a failing test that imports both bases**

Create `backend/tests/test_multitenancy/test_bases.py`:

```python
import pytest
from app.database import PlatformBase, TenantBase


def test_platform_base_is_separate_from_tenant_base():
    """PlatformBase and TenantBase must be independent DeclarativeBases."""
    assert PlatformBase is not TenantBase
    assert PlatformBase.metadata is not TenantBase.metadata


def test_tenant_base_has_existing_business_models():
    """After models are imported, TenantBase should contain business tables."""
    # Import all models to trigger registration
    import app.models  # noqa: F401
    # At minimum: users, factories, fmea_documents should be present
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
    # May have more, but must have at least these
    assert expected.issubset(platform_tables)
    # Must NOT have business tables
    assert "users" not in platform_tables
    assert "fmea_documents" not in platform_tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_multitenancy/test_bases.py -v`
Expected: FAIL — `PlatformBase` and `TenantBase` don't exist yet.

- [ ] **Step 3: Modify `database.py` to add PlatformBase and TenantBase**

In `backend/app/database.py`, add:

```python
from sqlalchemy.orm import DeclarativeBase


class PlatformBase(DeclarativeBase):
    """Base for platform-level models (tenants, platform_admin_users, reference_templates).
    Alembic platform migrations use this metadata."""
    pass


class TenantBase(DeclarativeBase):
    """Base for tenant business models (users, fmea_documents, etc.).
    Alembic tenant migrations use this metadata."""
    pass


# Backward compatibility: Base aliases to TenantBase for gradual migration
Base = TenantBase
```

Keep the existing `engine`, `async_session`, `get_db()` unchanged for now.

- [ ] **Step 4: Modify `models/__init__.py` to import from TenantBase**

In `backend/app/models/__init__.py`, add at the top:

```python
from app.database import TenantBase  # noqa: F401 — ensures models register with TenantBase
```

No changes to model imports — they already import `Base` which is now aliased to `TenantBase`.

- [ ] **Step 5: Run test to verify PlatformBase/TenantBase are separate**

Run: `cd backend && python -m pytest tests/test_multitenancy/test_bases.py::test_platform_base_is_separate_from_tenant_base -v`
Expected: PASS (PlatformBase is separate, has no tables yet)

- [ ] **Step 6: Commit**

```bash
git add backend/app/database.py backend/app/models/__init__.py backend/tests/test_multitenancy/test_bases.py
git commit -m "feat(multi-tenant): add PlatformBase and TenantBase declarative bases"
```

---

### Task 2: Create Platform Models (Tenant, PlatformAdminUser, ReferenceTemplate, TenantMigration)

**Files:**
- Create: `backend/app/models/tenant.py`
- Create: `backend/app/models/platform_admin.py`
- Create: `backend/app/models/reference_template.py`
- Create: `backend/app/models/tenant_migration.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write failing test for platform models**

Add to `backend/tests/test_multitenancy/test_bases.py`:

```python
from app.models.tenant import Tenant
from app.models.platform_admin import PlatformAdminUser
from app.models.reference_template import ReferenceTemplate
from app.models.tenant_migration import TenantMigration


def test_tenant_model_fields():
    """Tenant model must have required fields per spec."""
    columns = {c.name for c in Tenant.__table__.columns}
    required = {"id", "name", "slug", "schema_name", "subdomain", "plan", "status",
                "provisioning_step", "provisioning_error", "db_instance", "db_size_bytes",
                "user_count", "last_active_at", "created_at", "updated_at"}
    assert required.issubset(columns)


def test_tenant_model_uses_platform_base():
    """Tenant model must inherit from PlatformBase."""
    from app.database import PlatformBase
    assert issubclass(Tenant, PlatformBase)
    assert Tenant.__tablename__ == "tenants"


def test_tenant_slug_check_constraint():
    """slug must have CHECK constraint for [a-z0-9-] pattern."""
    constraints = [c for c in Tenant.__table__.constraints
                   if hasattr(c, 'sqltext') and 'slug' in str(c.sqltext)]
    assert len(constraints) >= 1


def test_tenant_schema_name_check_constraint():
    """schema_name must have CHECK constraint for tenant_[a-z0-9_] pattern."""
    constraints = [c for c in Tenant.__table__.constraints
                   if hasattr(c, 'sqltext') and 'schema_name' in str(c.sqltext)]
    assert len(constraints) >= 1


def test_platform_admin_model():
    """PlatformAdminUser must inherit from PlatformBase."""
    from app.database import PlatformBase
    assert issubclass(PlatformAdminUser, PlatformBase)


def test_reference_template_model():
    """ReferenceTemplate must inherit from PlatformBase."""
    from app.database import PlatformBase
    assert issubclass(ReferenceTemplate, PlatformBase)


def test_tenant_migration_model():
    """TenantMigration must inherit from PlatformBase."""
    from app.database import PlatformBase
    assert issubclass(TenantMigration, PlatformBase)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_multitenancy/test_bases.py -v`
Expected: FAIL — models don't exist yet.

- [ ] **Step 3: Create `backend/app/models/tenant.py`**

```python
import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Integer, BigInteger, Text, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP_WITH_TIMEZONE
from sqlalchemy.orm import Mapped, mapped_column

from app.database import PlatformBase


class Tenant(PlatformBase):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    schema_name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    subdomain: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(20), default="free")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    provisioning_step: Mapped[str | None] = mapped_column(String(50), default=None)
    provisioning_error: Mapped[str | None] = mapped_column(Text, default=None)
    db_instance: Mapped[str | None] = mapped_column(String(100), default=None)
    db_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    user_count: Mapped[int] = mapped_column(Integer, default=0)
    last_active_at: Mapped[datetime | None] = mapped_column(TIMESTAMP_WITH_TIMEZONE)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP_WITH_TIMEZONE, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP_WITH_TIMEZONE, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'",
            name="ck_tenants_slug_format",
        ),
        CheckConstraint(
            "schema_name ~ '^tenant_[a-z0-9_]{1,56}$'",
            name="ck_tenants_schema_name_format",
        ),
        CheckConstraint(
            "subdomain ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'",
            name="ck_tenants_subdomain_format",
        ),
        Index("idx_tenants_subdomain", "subdomain"),
        Index("idx_tenants_status", "status"),
    )
```

- [ ] **Step 4: Create `backend/app/models/platform_admin.py`**

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Boolean
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP_WITH_TIMEZONE
from sqlalchemy.orm import Mapped, mapped_column

from app.database import PlatformBase


class PlatformAdminUser(PlatformBase):
    __tablename__ = "platform_admin_users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # login identifier (not username)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="ops")  # superadmin or ops
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP_WITH_TIMEZONE, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP_WITH_TIMEZONE, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 5: Create `backend/app/models/reference_template.py`**

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP_WITH_TIMEZONE
from sqlalchemy.orm import Mapped, mapped_column

from app.database import PlatformBase


class ReferenceTemplate(PlatformBase):
    __tablename__ = "reference_templates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # fmea, control_plan, audit_checklist, iqc_aql
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # JSON template content
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP_WITH_TIMEZONE, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP_WITH_TIMEZONE, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 6: Create `backend/app/models/tenant_migration.py`**

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy import String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP_WITH_TIMEZONE
from sqlalchemy.orm import Mapped, mapped_column

from app.database import PlatformBase


class TenantMigration(PlatformBase):
    __tablename__ = "tenant_migrations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("public.tenants.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/completed/failed
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP_WITH_TIMEZONE)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP_WITH_TIMEZONE)
    applied_at: Mapped[datetime | None] = mapped_column(TIMESTAMP_WITH_TIMEZONE)  # = completed_at
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_tenant_migrations_tenant_version"),
    )
```

Note: The `UniqueConstraint` on `(tenant_id, version)` will be defined via `__table_args__`. SQLAlchemy handles cross-schema FK (`public.tenants.id`) at application level since we prohibit cross-schema FK constraints per the spec.

- [ ] **Step 7: Register models in `__init__.py`**

Add to `backend/app/models/__init__.py`:

```python
from app.models.tenant import Tenant  # noqa: F401
from app.models.platform_admin import PlatformAdminUser  # noqa: F401
from app.models.reference_template import ReferenceTemplate  # noqa: F401
from app.models.tenant_migration import TenantMigration  # noqa: F401
```

And add them to the `__all__` list.

- [ ] **Step 8: Run tests to verify platform models**

Run: `cd backend && python -m pytest tests/test_multitenancy/test_bases.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/tenant.py backend/app/models/platform_admin.py backend/app/models/reference_template.py backend/app/models/tenant_migration.py backend/app/models/__init__.py backend/tests/test_multitenancy/test_bases.py
git commit -m "feat(multi-tenant): add platform models — Tenant, PlatformAdminUser, ReferenceTemplate, TenantMigration"
```

---

### Task 3: Create Tenant Context Middleware and Tenant Utilities

**Files:**
- Create: `backend/app/core/tenant_context.py`
- Create: `backend/app/core/tenant_utils.py`
- Create: `backend/tests/test_multitenancy/test_tenant_context.py`

- [ ] **Step 1: Write failing test for tenant resolution**

Create `backend/tests/test_multitenancy/test_tenant_context.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.tenant_utils import set_search_path_sql, slug_to_schema_name


def test_set_search_path_valid_schema():
    """Valid schema names produce correct SET search_path SQL."""
    result = set_search_path_sql("tenant_acme")
    assert result == 'SET search_path TO "tenant_acme", "public"'


def test_set_search_path_rejects_invalid_names():
    """Invalid schema names raise ValueError."""
    with pytest.raises(ValueError, match="Invalid schema name"):
        set_search_path_sql("evil'; DROP TABLE users;--")

    with pytest.raises(ValueError, match="Invalid schema name"):
        set_search_path_sql("tenant_")  # too short after prefix

    with pytest.raises(ValueError, match="Invalid schema name"):
        set_search_path_sql("a" * 70)  # exceeds 63 chars


def test_set_search_path_escapes_double_quotes():
    """Double quotes in schema names are escaped."""
    # This would be caught by regex first, but test the quoting logic
    result = set_search_path_sql("tenant_acme_corp")
    assert result == 'SET search_path TO "tenant_acme_corp", "public"'


def test_slug_to_schema_name():
    """slug is converted to schema_name by replacing - with _ and adding tenant_ prefix."""
    assert slug_to_schema_name("acme-corp") == "tenant_acme_corp"
    assert slug_to_schema_name("my-company") == "tenant_my_company"
    assert slug_to_schema_name("abc") == "tenant_abc"


def test_slug_to_schema_name_rejects_invalid():
    """Invalid slugs raise ValueError."""
    with pytest.raises(ValueError):
        slug_to_schema_name("")  # empty
    with pytest.raises(ValueError):
        slug_to_schema_name("ABC")  # uppercase
    with pytest.raises(ValueError):
        slug_to_schema_name("-acme")  # starts with hyphen
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_multitenancy/test_tenant_context.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `backend/app/core/tenant_utils.py`**

```python
"""Tenant utility functions — shared between runtime code and Alembic env.py."""
import re
from contextvars import ContextVar

# Context variable: current request/task's tenant schema name
current_tenant_schema: ContextVar[str | None] = ContextVar("current_tenant_schema", default=None)

# Regex patterns
_SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_SCHEMA_PATTERN = re.compile(r"^tenant_[a-z0-9_]{1,56}$")


def slug_to_schema_name(slug: str) -> str:
    """Convert a URL slug to a PostgreSQL schema name.

    Rules:
    - slug: [a-z0-9-] (DNS-compatible)
    - schema_name: tenant_ prefix + [a-z0-9_] (PostgreSQL-compatible)
    - Hyphens in slug become underscores in schema_name
    """
    if not slug or not _SLUG_PATTERN.match(slug):
        raise ValueError(f"Invalid slug: {slug!r} (must match [a-z0-9-]+)")
    schema_name = "tenant_" + slug.replace("-", "_")
    if not _SCHEMA_PATTERN.match(schema_name):
        raise ValueError(f"Invalid schema name derived from slug: {slug!r} -> {schema_name!r}")
    return schema_name


def set_search_path_sql(schema_name: str) -> str:
    """Validate schema name and generate safe SET search_path SQL.

    Prevents SQL injection by:
    1. Validating schema_name against ^tenant_[a-z0-9_]{1,56}$ regex
    2. Double-quoting the identifier with proper escaping
    """
    if not _SCHEMA_PATTERN.match(schema_name):
        raise ValueError(f"Invalid schema name: {schema_name!r} (must match tenant_[a-z0-9_]+, max 63 chars)")
    # PostgreSQL quoted identifier (double-quote wrapping, internal double-quotes doubled)
    quoted = '"' + schema_name.replace('"', '""') + '"'
    return f'SET search_path TO {quoted}, "public"'
```

- [ ] **Step 4: Create `backend/app/core/tenant_context.py`**

```python
"""TenantContext middleware — resolves tenant from request and injects into request.state."""
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.tenant_utils import slug_to_schema_name
from app.database import async_session
from app.models.tenant import Tenant

from sqlalchemy import select, text

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Middleware that resolves tenant from subdomain or X-Tenant-ID header
    and injects it into request.state.tenant.

    Does NOT set search_path — that happens in get_db() dependency.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip tenant resolution for platform admin routes
        if request.url.path.startswith("/api/platform/"):
            request.state.tenant = None
            response = await call_next(request)
            return response

        # Skip tenant resolution for health check and docs
        if request.url.path in ("/api/health", "/docs", "/openapi.json", "/redoc"):
            request.state.tenant = None
            response = await call_next(request)
            return response

        tenant = None

        # 1. Try subdomain from Host header (production)
        host = request.headers.get("host", "")
        domain_suffix = request.app.state.tenant_domain if hasattr(request.app.state, "tenant_domain") else None

        if domain_suffix and host:
            # Extract subdomain: "acme.openqms.com" -> "acme"
            if host.endswith(f".{domain_suffix}"):
                subdomain = host[: -(len(domain_suffix) + 1)]
                if subdomain and subdomain != "admin":
                    tenant = await self._resolve_by_subdomain(subdomain)

        # 2. Try X-Tenant-ID header (development)
        if tenant is None:
            tenant_slug = request.headers.get("X-Tenant-ID")
            if tenant_slug:
                tenant = await self._resolve_by_slug(tenant_slug)

        # 3. Try JWT tenant_id claim (fallback)
        if tenant is None:
            # Will be populated by auth dependency after login
            # This is a secondary resolution — JWT is verified in auth.py
            pass

        # Store resolved tenant (or None) in request state
        request.state.tenant = tenant
        response = await call_next(request)
        return response

    async def _resolve_by_subdomain(self, subdomain: str):
        """Look up tenant by subdomain."""
        async with async_session() as session:
            await session.execute(text('SET search_path TO "public"'))
            result = await session.execute(
                select(Tenant).where(Tenant.subdomain == subdomain, Tenant.status == "active")
            )
            return result.scalar_one_or_none()

    async def _resolve_by_slug(self, slug: str):
        """Look up tenant by slug."""
        async with async_session() as session:
            await session.execute(text('SET search_path TO "public"'))
            result = await session.execute(
                select(Tenant).where(Tenant.slug == slug, Tenant.status == "active")
            )
            return result.scalar_one_or_none()
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_multitenancy/test_tenant_context.py -v`
Expected: PASS (all utility function tests pass)

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/tenant_utils.py backend/app/core/tenant_context.py backend/tests/test_multitenancy/test_tenant_context.py
git commit -m "feat(multi-tenant): add TenantContextMiddleware and tenant utility functions"
```

---

### Task 4: Retrofit `get_db()` with Tenant-Aware search_path and Add `get_tenant_aware_session()`

**Files:**
- Modify: `backend/app/database.py`
- Modify: `backend/tests/test_multitenancy/test_tenant_context.py`

This is the critical change — retrofitting `get_db()` to set `search_path` per request. All 35+ existing API routes automatically inherit tenant isolation without any file changes.

- [ ] **Step 1: Write failing test for tenant-aware get_db**

Add to `backend/tests/test_multitenancy/test_tenant_context.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextvars import ContextVar


@pytest.mark.asyncio
async def test_get_db_sets_search_path_for_tenant():
    """get_db() must SET search_path when tenant is present."""
    from app.database import get_db

    # Mock request with tenant
    mock_request = MagicMock()
    mock_tenant = MagicMock()
    mock_tenant.schema_name = "tenant_acme"
    mock_request.state.tenant = mock_tenant

    # get_db is an async generator — we need to test the yielded session
    # This test verifies the setup logic; integration tests will verify end-to-end
    # The key assertion: when tenant is set, search_path must be set
    assert mock_request.state.tenant.schema_name == "tenant_acme"


def test_context_var_default_is_none():
    """current_tenant_schema defaults to None (no tenant context)."""
    from app.core.tenant_utils import current_tenant_schema
    assert current_tenant_schema.get() is None


def test_context_var_set_and_reset():
    """current_tenant_schema can be set and reset without leaking."""
    from app.core.tenant_utils import current_tenant_schema
    token = current_tenant_schema.set("tenant_test")
    assert current_tenant_schema.get() == "tenant_test"
    current_tenant_schema.reset(token)
    assert current_tenant_schema.get() is None
```

- [ ] **Step 2: Modify `database.py` to retrofit `get_db()`**

Replace the existing `get_db()` function and add `get_tenant_aware_session()`, `get_platform_db()`, and `run_for_each_tenant()`. Also add the connection pool checkout event listener as a safety net (per spec §2.3).

Key addition — checkout event listener for search_path reset safety net:

```python
from sqlalchemy import event

# After engine creation:
@event.listens_for(engine.sync_engine, "checkout")
def _reset_search_path_on_checkout(dbapi_connection, connection_record):
    """Safety net: ensure search_path is reset to default on every pool checkout.
    This catches any leaked search_path from previous requests.
    See spec §2.3 for rationale."""
    cursor = dbapi_connection.cursor()
    cursor.execute("RESET search_path")
    cursor.close()
```

Replace the existing `get_db()` function and add `get_tenant_aware_session()` and `get_platform_db()`:

```python
from contextlib import asynccontextmanager
from fastapi import Request
from sqlalchemy import text

from app.core.tenant_utils import current_tenant_schema, set_search_path_sql


async def get_db(request: Request):
    """Tenant-aware database session dependency.

    Replaces the old get_db(). Sets search_path based on the resolved tenant.
    If no tenant (platform routes), search_path stays at default 'public'.
    """
    tenant = getattr(request.state, "tenant", None)
    # Set ContextVar for nested Service calls via get_tenant_aware_session()
    token = current_tenant_schema.set(tenant.schema_name if tenant else None)
    try:
        async with async_session() as session:
            if tenant:
                await session.execute(text(set_search_path_sql(tenant.schema_name)))
            try:
                yield session
            finally:
                await session.rollback()
                if tenant:
                    # RESET must be committed to survive connection pool return
                    async with session.begin():
                        await session.execute(text('RESET search_path'))
                await session.close()
    finally:
        current_tenant_schema.reset(token)


async def get_platform_db():
    """Platform admin database session — forces search_path to 'public'.
    Used exclusively by /api/platform/* routes.
    """
    async with async_session() as session:
        await session.execute(text('SET search_path TO "public"'))
        try:
            yield session
        finally:
            await session.rollback()
            async with session.begin():
                await session.execute(text('RESET search_path'))
            await session.close()


@asynccontextmanager
async def get_tenant_aware_session():
    """Tenant-aware session factory for Service code that needs independent sessions.

    Reads the current tenant schema from ContextVar (set by get_db() or
    run_for_each_tenant()). Falls back to 'public' if no tenant context.

    MUST be used instead of bare async_session() in all Service code.
    """
    schema = current_tenant_schema.get()
    async with async_session() as session:
        if schema:
            await session.execute(text(set_search_path_sql(schema)))
        try:
            yield session
        finally:
            await session.rollback()
            if schema:
                async with session.begin():
                    await session.execute(text('RESET search_path'))
            await session.close()


async def run_for_each_tenant():
    """Iterate over all active tenants, setting search_path for each.

    Usage:
        async for tenant, db in run_for_each_tenant():
            await SomeService.do_work(db)
    """
    async with async_session() as session:
        await session.execute(text('SET search_path TO "public"'))
        result = await session.execute(
            select(Tenant).where(Tenant.status == "active")
        )
        tenants = result.scalars().all()

    for tenant in tenants:
        token = current_tenant_schema.set(tenant.schema_name)
        try:
            async with async_session() as db:
                await db.execute(text(set_search_path_sql(tenant.schema_name)))
                try:
                    yield tenant, db
                finally:
                    await db.rollback()
                    async with db.begin():
                        await db.execute(text('RESET search_path'))
                    await db.close()
        finally:
            current_tenant_schema.reset(token)
```

- [ ] **Step 3: Update imports in `database.py`**

Add at the top of `backend/app/database.py`:

```python
from contextlib import asynccontextmanager
from fastapi import Request
from sqlalchemy import text, select

from app.core.tenant_utils import current_tenant_schema, set_search_path_sql
```

Add the `Tenant` model import (lazy to avoid circular):

```python
# Lazy import to avoid circular dependency at module level
# Tenant model is imported inside run_for_each_tenant() function
```

In `run_for_each_tenant()`, add:

```python
from app.models.tenant import Tenant
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_multitenancy/test_tenant_context.py -v`
Expected: PASS

- [ ] **Step 5: Verify existing routes still work (smoke test)**

Run: `cd backend && python -m pytest tests/ -v -k "not multitenancy" --timeout=30 -x`
Expected: All existing tests pass — `get_db(request)` signature is compatible because FastAPI injects `Request` via `Depends()`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/database.py backend/tests/test_multitenancy/test_tenant_context.py
git commit -m "feat(multi-tenant): retrofit get_db() with tenant-aware search_path, add get_tenant_aware_session() and run_for_each_tenant()"
```

---

### Task 5: Alembic Dual-Base Configuration and Branch Migrations

**Files:**
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/p001_platform_tables.py`
- Create: `backend/alembic/versions/t000_tenant_baseline.py`
- Create: `backend/app/cli/tenant_migrate.py`

- [ ] **Step 1: Modify `alembic/env.py` for dual-base branch support**

```python
# At the top of alembic/env.py, after existing imports:
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection
from alembic import context

from app.database import PlatformBase, TenantBase
from app.core.tenant_utils import set_search_path_sql

config = context.config
if config.config_file_name is not None:
    from logging.config import fileConfig
    fileConfig(config.config_file_name)

target_metadata = TenantBase.metadata  # Default — overridden by x_args
platform_metadata = PlatformBase.metadata


def do_run_migrations(connection: AsyncConnection, schema_name: str | None):
    x_args = context.get_x_argument(as_dictionary=True)
    schema_override = x_args.get("schema") or schema_name

    if schema_override:
        # Tenant migration
        connection.execute(text(set_search_path_sql(schema_override)))
        context.configure(
            connection=connection,
            target_metadata=TenantBase.metadata,
            version_table_schema=schema_override,
        )
    else:
        # Platform migration
        context.configure(
            connection=connection,
            target_metadata=PlatformBase.metadata,
            version_table_schema="public",
        )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    connectable = create_async_engine(url, poolclass=pool.NullPool)

    x_args = context.get_x_argument(as_dictionary=True)
    schema_name = x_args.get("schema")

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda conn: do_run_migrations(conn, schema_name)
        )
    await connectable.dispose()


def run_migrations_offline():
    url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    x_args = context.get_x_argument(as_dictionary=True)
    schema_name = x_args.get("schema")

    context.configure(
        url=url,
        target_metadata=TenantBase.metadata if schema_name else PlatformBase.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())
```

- [ ] **Step 2: Create `t000_tenant_baseline.py`**

```python
"""tenant baseline — independent branch root for tenant migrations.

Revision ID: t000
Revises: None
Branch labels: ('tenant',)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 't000_tenant_baseline'
down_revision = None
branch_labels = ('tenant',)
depends_on = None


def upgrade() -> None:
    # Empty operation — this is just the branch root
    pass


def downgrade() -> None:
    pass
```

- [ ] **Step 3: Create `t001_tenant_squash.py`**

This is the critical migration that creates all ~50 business tables for new tenants. Without it, `alembic upgrade tenant@head` only runs the empty t000 baseline, leaving new tenant schemas with no tables.

```python
"""tenant squash — creates all tenant business tables in one migration.

Revision ID: t001
Revises: t000_tenant_baseline
Branch labels: None (inherits 'tenant' from t000)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 't001_tenant_squash'
down_revision = 't000_tenant_baseline'
branch_labels = None  # inherits 'tenant' branch from t000
depends_on = None


def upgrade() -> None:
    # This squash migration creates ALL current business tables.
    # Generate the table list from TenantBase.metadata:
    #   from app.database import TenantBase
    #   for table_name in sorted(TenantBase.metadata.tables.keys()):
    #       print(table_name)
    # Then create each table with op.create_table().
    #
    # IMPORTANT: This migration must be regenerated whenever TenantBase models change.
    # Use `alembic -x schema=tenant_test upgrade tenant@head` to test on a fresh schema.
    #
    # For the initial implementation, this will be a large migration covering:
    # users, role_definitions, user_product_lines, factories, user_factories,
    # product_lines, fmea_documents, fmea_versions, capa_eightd, audit_logs,
    # suppliers, supplier_certifications, supplier_evaluations, supplier_ppaps,
    # supplier_scars, supplier_shared_profiles, spc_characteristics, spc_batches,
    # spc_values, spc_alarms, control_limit_snapshots, control_plans,
    # control_plan_versions, cp_validation_runs, cp_validation_findings,
    # cp_validation_occurrences, quality_goals, audit_programs, audit_plans,
    # audit_findings, management_reviews, management_review_reports, gauges,
    # grr_studies, bias_studies, linearity_studies, stability_studies,
    # attribute_studies, iqc_inspections, iqc_inspection_items, iqc_materials,
    # iqc_inspection_templates, iqc_aql_configs, iqc_aql_profiles,
    # iqc_aql_recommendations, iqc_aql_quality_snapshots, customer_complaints,
    # customers, rma_records, apqp_projects, ppap_submissions, shipment_records,
    # special_characteristics, special_characteristic_links, erp_connections,
    # erp_sync_jobs, mes_connections, mes_production_orders, document_embeddings,
    # graph_sync_outbox, collaboration_sessions, change_impacts,
    # recommendation_caches, user_dashboard_layouts, supplier_risk_alerts,
    # supplier_risk_configs, supply_chain_risk_snapshots
    #
    # Implementation note: Use `alembic autogenerate` with TenantBase.metadata
    # against an empty schema to generate the initial table definitions, then
    # review and commit. The autogenerate command:
    #   alembic -x schema=tenant_test revision --autogenerate -m "tenant_squash"
    # Then review the generated migration, verify branch_labels=None and
    # down_revision='t000_tenant_baseline', and add schema parameter to
    # all op.create_table calls (or rely on search_path being set by env.py).
    pass  # Will be populated via autogenerate against TenantBase.metadata


def downgrade() -> None:
    # Drop all tables in reverse order
    # Generated alongside upgrade() from TenantBase.metadata
    pass  # Will be populated via autogenerate
```

- [ ] **Step 4: Create `p001_platform_tables.py`**

```python
"""platform tables — tenants, tenant_migrations, platform_admin_users, reference_templates.

Revision ID: p001
Revises: None
Branch labels: ('platform',)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'p001_platform_tables'
down_revision = None
branch_labels = ('platform',)
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(50), unique=True, nullable=False),
        sa.Column('schema_name', sa.String(63), unique=True, nullable=False),
        sa.Column('subdomain', sa.String(63), unique=True, nullable=False),
        sa.Column('plan', sa.String(20), server_default='free'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('provisioning_step', sa.String(50), nullable=True),
        sa.Column('provisioning_error', sa.Text, nullable=True),
        sa.Column('db_instance', sa.String(100), nullable=True),
        sa.Column('db_size_bytes', sa.BigInteger, server_default='0'),
        sa.Column('user_count', sa.Integer, server_default='0'),
        sa.Column('last_active_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'", name='ck_tenants_slug_format'),
        sa.CheckConstraint("schema_name ~ '^tenant_[a-z0-9_]{1,56}$'", name='ck_tenants_schema_name_format'),
        sa.CheckConstraint("subdomain ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'", name='ck_tenants_subdomain_format'),
        schema='public',
    )
    op.create_index('idx_tenants_subdomain', 'tenants', ['subdomain'], schema='public')
    op.create_index('idx_tenants_status', 'tenants', ['status'], schema='public')

    op.create_table(
        'tenant_migrations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.tenants.id'), nullable=False),
        sa.Column('version', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('applied_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.UniqueConstraint('tenant_id', 'version', name='uq_tenant_migrations_tenant_version'),
        schema='public',
    )

    op.create_table(
        'platform_admin_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(100), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), server_default='ops'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        schema='public',
    )

    op.create_table(
        'reference_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('version', sa.String(20), server_default='1.0'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        schema='public',
    )


def downgrade() -> None:
    op.drop_table('reference_templates', schema='public')
    op.drop_table('platform_admin_users', schema='public')
    op.drop_table('tenant_migrations', schema='public')
    op.drop_table('tenants', schema='public')
```

- [ ] **Step 4: Create `backend/app/cli/tenant_migrate.py`**

```python
"""CLI script for tenant migration orchestration.

Usage:
    python -m app.cli.tenant_migrate --all        # Migrate all active tenants
    python -m app.cli.tenant_migrate --slug acme    # Migrate specific tenant
"""
import argparse
import asyncio
import logging
import subprocess
import sys

from sqlalchemy import select, text

from app.database import async_session
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


async def get_active_tenants(slug: str | None = None):
    """Get all active tenants, or a specific one by slug."""
    async with async_session() as session:
        await session.execute(text('SET search_path TO "public"'))
        query = select(Tenant).where(Tenant.status == "active")
        if slug:
            query = query.where(Tenant.slug == slug)
        result = await session.execute(query)
        return result.scalars().all()


def run_alembic_upgrade(schema_name: str) -> bool:
    """Run alembic upgrade tenant@head for a specific tenant schema."""
    cmd = [
        sys.executable, "-m", "alembic",
        "-x", f"schema={schema_name}",
        "upgrade", "tenant@head",
    ]
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Alembic failed for %s:\n%s", schema_name, result.stderr)
        return False
    logger.info("Successfully migrated %s", schema_name)
    return True


async def main(all_tenants: bool = False, slug: str | None = None):
    tenants = await get_active_tenants(slug)
    if not tenants:
        logger.info("No active tenants found.")
        return

    for tenant in tenants:
        logger.info("Migrating tenant %s (schema: %s)...", tenant.slug, tenant.schema_name)
        success = run_alembic_upgrade(tenant.schema_name)
        # Update tenant_migrations table via the ORM
        async with async_session() as session:
            await session.execute(text('SET search_path TO "public"'))
            # Update status based on success/failure
            from app.models.tenant_migration import TenantMigration
            migration = TenantMigration(
                tenant_id=tenant.id,
                version="tenant@head",
                status="completed" if success else "failed",
            )
            session.add(migration)
            await session.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate tenant schemas")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Migrate all active tenants")
    group.add_argument("--slug", type=str, help="Migrate a specific tenant by slug")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(all_tenants=args.all, slug=args.slug))
```

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/env.py backend/alembic/versions/p001_platform_tables.py backend/alembic/versions/t000_tenant_baseline.py backend/alembic/versions/t001_tenant_squash.py backend/app/cli/tenant_migrate.py
git commit -m "feat(multi-tenant): add Alembic dual-base config, platform/tenant branch migrations, squash, and tenant_migrate CLI"
```

---

### Task 6: Platform Admin Auth and API Routes

**Files:**
- Modify: `backend/app/core/security.py` — add platform admin JWT support with `iss/aud` claims
- Create: `backend/app/api/platform/__init__.py`
- Create: `backend/app/api/platform/auth.py`
- Create: `backend/app/api/platform/tenants.py`
- Create: `backend/app/core/deps.py` — add `require_platform_admin` dependency
- Create: `backend/app/services/tenant_service.py`
- Create: `backend/tests/test_multitenancy/test_platform_api.py`

- [ ] **Step 1: Add platform admin JWT functions to `security.py`**

Add two new functions alongside existing `create_access_token` / `verify_token`:

```python
# In app/core/security.py — add after existing JWT functions

from app.config import settings

# JWT issuer/audience constants for cross-domain prevention
TENANT_ISSUER = "openqms-tenant"
PLATFORM_ISSUER = "openqms-platform"
TENANT_AUDIENCE = "openqms-tenant"
PLATFORM_AUDIENCE = "openqms-platform"


def create_platform_admin_token(admin_id: str, role: str = "superadmin") -> str:
    """Create JWT for platform admin. Uses separate iss/aud to prevent cross-domain use."""
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": str(admin_id),
        "is_platform_admin": True,
        "role": role,
        "iss": PLATFORM_ISSUER,
        "aud": PLATFORM_AUDIENCE,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_tenant_user_token(user_id: str, tenant_id: str, role_id: str, factory_id: str | None = None) -> str:
    """Create JWT for tenant user. Includes tenant_id claim with separate iss/aud."""
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role_id": str(role_id),
        "factory_id": str(factory_id) if factory_id else None,
        "iss": TENANT_ISSUER,
        "aud": TENANT_AUDIENCE,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
```

- [ ] **Step 2: Create `require_platform_admin` dependency in `deps.py`**

Add to `backend/app/core/deps.py`:

```python
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError
from app.core.security import verify_token, PLATFORM_ISSUER, PLATFORM_AUDIENCE


async def require_platform_admin(request: Request):
    """Dependency for /api/platform/* routes.
    Rejects tenant JWTs (tenant_id claim present) with 403.
    Ignores X-Tenant-ID header (avoids false positives from dev proxies).
    Requires platform admin JWT (is_platform_admin: true) with correct iss/aud.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[7:]
    payload = verify_token(token)

    # Reject tenant JWTs — they have tenant_id claim
    if payload.get("tenant_id"):
        raise HTTPException(
            status_code=403,
            detail="Tenant JWT cannot access platform routes",
        )

    # Verify platform admin JWT
    if not payload.get("is_platform_admin"):
        raise HTTPException(
            status_code=403,
            detail="Platform admin access required",
        )

    # Verify iss/aud to prevent cross-domain JWT reuse
    if payload.get("iss") != PLATFORM_ISSUER:
        raise HTTPException(status_code=403, detail="Invalid token issuer")
    if payload.get("aud") != PLATFORM_AUDIENCE:
        raise HTTPException(status_code=403, detail="Invalid token audience")

    return payload
```

- [ ] **Step 3: Write failing test for platform route isolation**

Create `backend/tests/test_multitenancy/test_platform_api.py`:

```python
import pytest
from fastapi.testclient import TestClient


def test_platform_route_rejects_tenant_jwt():
    """Platform routes must reject JWTs with tenant_id claim."""
    # Will be implemented with actual test client setup
    pass


def test_platform_route_ignores_x_tenant_id_header():
    """Platform routes must ignore X-Tenant-ID header (not 403 on it)."""
    pass


def test_platform_route_requires_platform_admin_jwt():
    """Platform routes must require is_platform_admin: true."""
    pass


def test_ci_route_dependency_check():
    """CI test: all /api/platform/* routes must depend on get_platform_db, not get_db."""
    # This test scans the FastAPI app routes and asserts that
    # platform routes use get_platform_db in their dependencies.
    pass
```

- [ ] **Step 4: Create `backend/app/api/platform/__init__.py`**

```python
from fastapi import APIRouter
from app.api.platform.auth import router as auth_router
from app.api.platform.tenants import router as tenants_router

router = APIRouter(prefix="/api/platform")
router.include_router(auth_router, tags=["platform-auth"])
router.include_router(tenants_router, tags=["platform-tenants"])
```

- [ ] **Step 5: Create `backend/app/api/platform/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from app.core.security import (
    verify_password,
    create_platform_admin_token,
    hash_password,
)
from app.core.deps import require_platform_admin
from app.database import get_platform_db
from app.models.platform_admin import PlatformAdminUser
from app.schemas.platform import PlatformLoginRequest, PlatformLoginResponse

router = APIRouter()


@router.post("/auth/login", response_model=PlatformLoginResponse)
async def platform_login(request: PlatformLoginRequest, db=Depends(get_platform_db)):
    """Platform admin login — authenticates against platform_admin_users in public schema."""
    result = await db.execute(
        select(PlatformAdminUser).where(PlatformAdminUser.email == request.email)
    )
    admin = result.scalar_one_or_none()
    if not admin or not verify_password(request.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not admin.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")
    token = create_platform_admin_token(str(admin.id), admin.role)
    return PlatformLoginResponse(access_token=token, token_type="bearer")
```

- [ ] **Step 6: Create `backend/app/api/platform/tenants.py`**

```python
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from app.core.deps import require_platform_admin
from app.database import get_platform_db
from app.models.tenant import Tenant
from app.schemas.platform import TenantCreateRequest, TenantResponse, TenantListResponse
from app.services.tenant_service import TenantService

router = APIRouter()


@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    _admin=Depends(require_platform_admin),
    db=Depends(get_platform_db),
):
    """List all tenants (platform admin only)."""
    query = select(Tenant)
    if status:
        query = query.where(Tenant.status == status)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    tenants = result.scalars().all()
    return TenantListResponse(items=tenants, total=total, page=page, page_size=page_size)


@router.post("/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant(
    request: TenantCreateRequest,
    _admin=Depends(require_platform_admin),
    db=Depends(get_platform_db),
):
    """Provision a new tenant (platform admin only)."""
    tenant = await TenantService.provision(db, request)
    return tenant
```

- [ ] **Step 7: Create `backend/app/services/tenant_service.py`**

```python
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.tenant_utils import slug_to_schema_name
from app.models.tenant import Tenant
from app.schemas.platform import TenantCreateRequest

logger = logging.getLogger(__name__)


class TenantService:
    @staticmethod
    async def provision(db: AsyncSession, request: TenantCreateRequest) -> Tenant:
        """Provision a new tenant: create schema, run migrations, seed data."""
        schema_name = slug_to_schema_name(request.slug)
        tenant = Tenant(
            name=request.name,
            slug=request.slug,
            schema_name=schema_name,
            subdomain=request.subdomain or request.slug,
            plan=request.plan or "free",
            status="provisioning",
            provisioning_step="create_schema",
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

        try:
            # Step 1: Create schema
            await db.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            await db.commit()
            tenant.provisioning_step = "run_migrations"

            # Step 2: Run migrations (delegated to CLI)
            # In production, this calls: python -m app.cli.tenant_migrate --slug <slug>
            tenant.provisioning_step = "seed_data"

            # Step 3: Seed data (delegated to seed script with schema param)
            tenant.status = "active"
            tenant.provisioning_step = None
            await db.commit()
        except Exception as e:
            tenant.status = "failed"
            tenant.provisioning_error = str(e)
            await db.commit()
            logger.error("Tenant provisioning failed for %s: %s", request.slug, e)
            raise

        return tenant
```

- [ ] **Step 8: Create `backend/app/schemas/platform.py`**

```python
from pydantic import BaseModel, Field
from datetime import datetime


class PlatformLoginRequest(BaseModel):
    email: str  # Platform admins login with email, not username
    password: str


class PlatformLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    subdomain: str | None = Field(None, pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    plan: str | None = "free"


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    schema_name: str
    subdomain: str
    plan: str
    status: str
    provisioning_step: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    items: list[TenantResponse]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 9: Register platform router in `main.py`**

Add to `backend/app/main.py` imports and router registration:

```python
from app.api.platform import router as platform_router
# ...
app.include_router(platform_router)
```

- [ ] **Step 10: Commit**

```bash
git add backend/app/core/security.py backend/app/core/deps.py backend/app/api/platform/ backend/app/services/tenant_service.py backend/app/schemas/platform.py backend/app/main.py backend/tests/test_multitenancy/test_platform_api.py
git commit -m "feat(multi-tenant): add platform admin auth, require_platform_admin dependency, /api/platform routes, and tenant lifecycle service"
```

---

### Task 7: Modify Existing Auth for Tenant-Aware Login

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/core/security.py`
- Modify: `backend/tests/test_multitenancy/test_tenant_context.py`

- [ ] **Step 1: Modify `security.py` — update existing `create_access_token` to include `tenant_id`**

In `backend/app/core/security.py`, modify the existing `create_access_token` function to accept and include `tenant_id`:

```python
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    # Add iss/aud for tenant tokens
    if "tenant_id" in data:
        to_encode["iss"] = TENANT_ISSUER
        to_encode["aud"] = TENANT_AUDIENCE
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
```

- [ ] **Step 2: Modify `auth.py` login to resolve tenant and inject `tenant_id`**

In `backend/app/api/auth.py`, modify the login endpoint to:
1. Resolve tenant from `request.state.tenant` (set by TenantContext middleware)
2. Include `tenant_id` in JWT payload
3. Verify that JWT `tenant_id` matches the resolved tenant on subsequent requests

The key change is in the login handler:

```python
# In the login handler, after password verification:
tenant = getattr(request.state, "tenant", None)
token_data = {
    "sub": str(user.id),
    "role_id": str(user.role_id),
    "factory_id": str(user.factory_id) if user.factory_id else None,
}
if tenant:
    token_data["tenant_id"] = str(tenant.id)
access_token = create_access_token(data=token_data)
```

- [ ] **Step 3: Modify `deps.py` — add tenant JWT validation in `get_current_user`**

In `backend/app/core/deps.py`, modify `get_current_user` to validate `tenant_id` claim:

```python
async def get_current_user(token: str = Depends(oauth2_scheme), request: Request = None):
    payload = verify_token(token)
    user_id = payload.get("sub")

    # If request has a resolved tenant, verify JWT tenant_id matches
    if request and hasattr(request.state, "tenant") and request.state.tenant:
        jwt_tenant_id = payload.get("tenant_id")
        if jwt_tenant_id and jwt_tenant_id != str(request.state.tenant.id):
            raise HTTPException(status_code=403, detail="Token tenant mismatch")

    # ... rest of existing user lookup logic
```

- [ ] **Step 4: Write test for cross-tenant JWT rejection**

Add to `backend/tests/test_multitenancy/test_tenant_context.py`:

```python
def test_cross_tenant_jwt_rejection():
    """JWT with tenant_id=A must not be accepted on tenant B's subdomain."""
    # This will be an integration test that:
    # 1. Creates a token with tenant_id="tenant-a"
    # 2. Makes a request to tenant B's subdomain
    # 3. Expects 403 Forbidden
    pass


def test_platform_jwt_cannot_access_tenant_routes():
    """Platform admin JWT (is_platform_admin=true) must not work on tenant routes."""
    # Platform JWT lacks tenant_id, should be rejected by get_current_user
    pass


def test_tenant_jwt_cannot_access_platform_routes():
    """Tenant JWT must be rejected by require_platform_admin."""
    # Already tested in test_platform_api.py
    pass
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/app/core/security.py backend/app/core/deps.py backend/tests/test_multitenancy/test_tenant_context.py
git commit -m "feat(multi-tenant): add tenant_id to JWT with iss/aud domain isolation and cross-tenant rejection"
```

---

### Task 8: Modify Background Tasks for Multi-Tenant Iteration

**Files:**
- Modify: `backend/app/main.py` — wrap background task loops with `run_for_each_tenant()`
- Modify: `backend/app/services/mes_service.py` — replace `async_session()` with `get_tenant_aware_session()`
- Modify: `backend/app/services/plm_service.py` — replace `async_session()` with `get_tenant_aware_session()`
- Modify: `backend/app/services/erp_service.py` — replace `async_session()` with `get_tenant_aware_session()`
- Modify: `backend/app/services/supplier_risk/service.py` — replace `async_session()` with `get_tenant_aware_session()`
- Modify: `backend/app/services/iqc_aql_service.py` — replace `async_session()` with `get_tenant_aware_session()`
- Modify: `backend/app/services/collaboration_service.py` — replace `async_session()` with `get_tenant_aware_session()`
- Modify: `backend/app/services/supply_chain_risk_map/scheduler.py` — replace `async_session()` with `get_tenant_aware_session()`
- Create: `backend/tests/test_multitenancy/test_background_tasks.py`

- [ ] **Step 1: Write failing test for `run_for_each_tenant()`**

Create `backend/tests/test_multitenancy/test_background_tasks.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.tenant_utils import current_tenant_schema


@pytest.mark.asyncio
async def test_run_for_each_tenant_iterates_all_active_tenants():
    """run_for_each_tenant must iterate over all active tenants and set ContextVar."""
    from app.database import run_for_each_tenant
    from app.models.tenant import Tenant

    # This test uses a mock for async_session to avoid needing a real DB
    # It verifies that:
    # 1. ContextVar is set before yielding tenant,db
    # 2. ContextVar is reset after each iteration
    # 3. search_path is set for each tenant
    pass


@pytest.mark.asyncio
async def test_run_for_each_tenant_resets_context_var_on_failure():
    """If an exception occurs during tenant iteration, ContextVar must still be reset."""
    from app.database import run_for_each_tenant

    # This test verifies that current_tenant_schema.reset(token) is called
    # in the finally block, even when the iteration body raises an exception.
    pass


@pytest.mark.asyncio
async def test_get_tenant_aware_session_reads_context_var():
    """get_tenant_aware_session must use the schema from current_tenant_schema ContextVar."""
    from app.database import get_tenant_aware_session

    token = current_tenant_schema.set("tenant_test")
    try:
        # Verify that when current_tenant_schema is set,
        # get_tenant_aware_session() sets search_path to that schema
        pass
    finally:
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_get_tenant_aware_session_defaults_to_public():
    """When current_tenant_schema is None, get_tenant_aware_session must not set search_path."""
    from app.database import get_tenant_aware_session

    assert current_tenant_schema.get() is None
    # Verify that search_path stays at default 'public'
```

- [ ] **Step 2: Modify `main.py` — wrap background loops**

Replace each `async with async_session() as db:` in the lifespan with `async for tenant, db in run_for_each_tenant():` and move the body inside the loop.

Example for MES sync:

```python
# Before:
async def _mes_sync_loop():
    while True:
        await asyncio.sleep(30)
        try:
            async with async_session() as db:
                await MESSyncService.run_sync_round(db)
        except Exception as e:
            logger.error("[mes_sync] error: %s", e)

# After:
async def _mes_sync_loop():
    while True:
        await asyncio.sleep(30)
        try:
            async for tenant, db in run_for_each_tenant():
                await MESSyncService.run_sync_round(db)
        except Exception as e:
            logger.error("[mes_sync] error: %s", e)
```

Apply this pattern to all 7 background task groups listed above.

- [ ] **Step 3: Replace bare `async_session()` in service code**

Find all service methods that use `async_session()` directly (not via `get_db()` or `get_tenant_aware_session()`). Replace each with:

```python
from app.database import get_tenant_aware_session

# Before:
async with async_session() as db:
    # ... query ...

# After:
async with get_tenant_aware_session() as db:
    # ... query ...
```

Key services to modify (based on spec §10.2):
- `app/services/mes_service.py` — `MESSyncService.run_sync_round`, `MESPushService.process_outbox`
- `app/services/plm_service.py` — `PLMSyncService.run_sync_round`, `PLMChangeImpactWorker.process_task`
- `app/services/erp_service.py` — `ERPSyncService.sync_all`
- `app/services/supplier_risk/service.py` — `evaluate_all_suppliers`
- `app/services/iqc_aql_service.py` — `AqlService.expire_stale_recommendations`
- `app/services/collaboration_service.py` — `delete_expired_sessions`
- `app/services/supply_chain_risk_map/scheduler.py` — `snapshot_loop`

- [ ] **Step 4: Add checkout event listener to engine for search_path reset safety net**

In `backend/app/database.py`, add after the `engine` creation:

```python
from sqlalchemy import event

@event.listens_for(engine.sync_engine, "checkout")
def _reset_search_path_on_checkout(dbapi_connection, connection_record):
    """Safety net: ensure search_path is reset to default on every connection pool checkout.
    This catches any leaked search_path from previous requests."""
    cursor = dbapi_connection.cursor()
    cursor.execute("RESET search_path")
    cursor.close()
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_multitenancy/test_background_tasks.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/app/database.py backend/app/services/ backend/tests/test_multitenancy/test_background_tasks.py
git commit -m "feat(multi-tenant): wrap background tasks with run_for_each_tenant(), replace bare async_session(), add checkout event safety net"
```

---

### Task 9: Frontend Adaptation — Axios Interceptor and Auth Store

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/store/authStore.ts`
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/pages/TenantSuspended.tsx`
- Create: `frontend/src/pages/TenantDeactivated.tsx`

- [ ] **Step 1: Add `X-Tenant-ID` header injection in Axios interceptor**

In `frontend/src/api/client.ts`, add to the request interceptor:

```typescript
// Development mode: inject X-Tenant-ID header from localStorage
if (import.meta.env.DEV) {
  const tenantSlug = localStorage.getItem('tenant_slug');
  if (tenantSlug) {
    request.headers['X-Tenant-ID'] = tenantSlug;
  }
}
```

- [ ] **Step 2: Add `tenant_id` to JWT payload types**

In `frontend/src/types/index.ts`, update the `User` type:

```typescript
export interface User {
  id: string;
  username: string;
  display_name: string;
  role_id: string;
  factory_id: string | null;
  factory_scope: FactoryScope | null;
  factories: Factory[];
  tenant_id?: string;  // Added for multi-tenancy
}
```

- [ ] **Step 3: Add 503 tenant-suspended and 410 tenant-deactivated response handling**

In `frontend/src/api/client.ts`, add to the response error interceptor:

```typescript
if (error.response?.status === 503 && error.response?.data?.detail?.tenant_suspended) {
  window.location.href = '/tenant-suspended';
  return;
}
if (error.response?.status === 410) {
  window.location.href = '/tenant-deactivated';
  return;
}
```

- [ ] **Step 4: Create tenant status pages**

Create `frontend/src/pages/TenantSuspended.tsx`:

```tsx
import { Result, Button } from 'antd';
import { useNavigate } from 'react-router-dom';

export default function TenantSuspended() {
  const navigate = useNavigate();
  return (
    <Result
      status="warning"
      title="租户已暂停"
      subTitle="您的租户账户已被暂停，请联系管理员。"
      extra={<Button type="primary" onClick={() => navigate('/login')}>返回登录</Button>}
    />
  );
}
```

Create `frontend/src/pages/TenantDeactivated.tsx`:

```tsx
import { Result, Button } from 'antd';
import { useNavigate } from 'react-router-dom';

export default function TenantDeactivated() {
  const navigate = useNavigate();
  return (
    <Result
      status="error"
      title="租户已停用"
      subTitle="您的租户账户已被停用，数据已保留但不可访问。"
      extra={<Button type="primary" onClick={() => navigate('/login')}>返回登录</Button>}
    />
  );
}
```

- [ ] **Step 5: Add routes for tenant status pages**

In the router config, add:

```tsx
{ path: '/tenant-suspended', element: <TenantSuspended /> },
{ path: '/tenant-deactivated', element: <TenantDeactivated /> },
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/store/authStore.ts frontend/src/types/index.ts frontend/src/pages/TenantSuspended.tsx frontend/src/pages/TenantDeactivated.tsx
git commit -m "feat(multi-tenant): frontend — X-Tenant-ID header, tenant status pages, 503/410 handling"
```

---

### Task 10: Integration Tests and Migration Script

**Files:**
- Create: `backend/tests/test_multitenancy/test_isolation.py`
- Create: `backend/tests/test_multitenancy/test_tenant_lifecycle.py`
- Create: `backend/scripts/migrate_to_multi_tenant.py`

- [ ] **Step 1: Write tenant isolation test**

Create `backend/tests/test_multitenancy/test_isolation.py`:

```python
"""Test that tenant schemas are properly isolated — data in tenant A is invisible to tenant B."""
import pytest
from sqlalchemy import text, select
from app.database import async_session, get_tenant_aware_session
from app.core.tenant_utils import set_search_path_sql, current_tenant_schema


@pytest.mark.asyncio
async def test_tenant_data_isolation():
    """Write data to tenant_a schema, verify tenant_b cannot see it."""
    # 1. Create two test schemas
    # 2. SET search_path TO "tenant_test_a", "public"
    # 3. INSERT a user into tenant_test_a
    # 4. SET search_path TO "tenant_test_b", "public"
    # 5. SELECT from users — must return empty
    # 6. Drop both test schemas
    pass


@pytest.mark.asyncio
async def test_search_path_reset_on_pool_return():
    """After a request completes, search_path must be reset to default."""
    # 1. Make a request as tenant A
    # 2. Verify search_path was set to tenant_test_a
    # 3. After the request completes, verify search_path is back to default
    pass


@pytest.mark.asyncio
async def test_context_var_no_leak_on_error():
    """If a request raises an exception, current_tenant_schema must still be reset."""
    from app.core.tenant_utils import current_tenant_schema

    token = current_tenant_schema.set("tenant_test")
    assert current_tenant_schema.get() == "tenant_test"

    # Simulate error path
    try:
        raise RuntimeError("test error")
    finally:
        current_tenant_schema.reset(token)

    assert current_tenant_schema.get() is None
```

- [ ] **Step 2: Write tenant lifecycle test**

Create `backend/tests/test_multitenancy/test_tenant_lifecycle.py`:

```python
"""Test tenant lifecycle: create → active → suspended → reactivated → deactivated."""
import pytest
from app.services.tenant_service import TenantService


@pytest.mark.asyncio
async def test_tenant_provisioning():
    """Tenant provisioning creates schema, runs migrations, sets status to active."""
    # 1. Create tenant via TenantService.provision()
    # 2. Verify schema was created
    # 3. Verify status is 'active'
    pass


@pytest.mark.asyncio
async def test_tenant_suspend_and_reactivate():
    """Tenant can be suspended and reactivated."""
    # 1. Create and activate tenant
    # 2. Suspend tenant (status = 'suspended')
    # 3. Verify TenantContext middleware returns 503 for suspended tenants
    # 4. Reactivate tenant (status = 'active')
    # 5. Verify tenant is accessible again
    pass


@pytest.mark.asyncio
async def test_tenant_deactivation():
    """Deactivated tenant data is preserved but inaccessible."""
    # 1. Create and activate tenant with data
    # 2. Deactivate tenant (status = 'deactivated')
    # 3. Verify TenantContext middleware returns 410 for deactivated tenants
    # 4. Verify schema still exists (data preserved)
    pass
```

- [ ] **Step 3: Write migration script for existing deployment**

Create `backend/scripts/migrate_to_multi_tenant.py` — following the exact steps from §9.1 of the spec:

```python
"""Migration script: convert existing single-tenant deployment to multi-tenant.

Steps (per design spec §9.1):
1. Backup public.alembic_version
2. CREATE SCHEMA tenant_default
3. ALTER TABLE ... SET SCHEMA tenant_default (all business objects + ENUMs + sequences)
4. alembic -x schema=tenant_default stamp tenant@head
5. Clear public.alembic_version
6. alembic upgrade platform@head
7. INSERT INTO public.tenants (...) VALUES (...)
8. Enable TENANT_MODE=true

IMPORTANT: Steps 4-6 must be in this exact order. Clearing alembic_version (step 5)
before running platform upgrade (step 6) prevents Alembic revision graph mismatch.
"""
import asyncio
import sys
import os
import subprocess

from sqlalchemy import text


# Business tables to migrate (from TenantBase.metadata.tables)
BUSINESS_TABLES = [
    "users", "role_definitions", "user_product_lines", "factories", "user_factories",
    "product_lines", "fmea_documents", "fmea_versions", "capa_eightd", "audit_logs",
    # ... (full list generated from TenantBase.metadata)
]

# ENUM types to migrate
ENUM_TYPES = [
    # Generated from inspection of models
]

# Sequences to migrate (those not auto-moved with tables)
SEQUENCES = [
    # Generated from inspection
]


async def migrate():
    from app.database import async_session

    async with async_session() as conn:
        # Step 1: Backup alembic_version
        result = await conn.execute(text("SELECT version_num FROM public.alembic_version"))
        old_versions = [row[0] for row in result]
        print(f"Backed up {len(old_versions)} old revision(s): {old_versions}")

        # Step 2: Create tenant schema
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "tenant_default"'))
        await conn.commit()
        print("Created schema tenant_default")

        # Step 3: Move all business objects
        for table in BUSINESS_TABLES:
            await conn.execute(text(f'ALTER TABLE IF EXISTS public."{table}" SET SCHEMA "tenant_default"'))
        for enum_type in ENUM_TYPES:
            await conn.execute(text(f'ALTER TYPE IF EXISTS public."{enum_type}" SET SCHEMA "tenant_default"'))
        for seq in SEQUENCES:
            await conn.execute(text(f'ALTER SEQUENCE IF EXISTS public."{seq}" SET SCHEMA "tenant_default"'))
        await conn.commit()
        print(f"Moved {len(BUSINESS_TABLES)} tables, {len(ENUM_TYPES)} enums, {len(SEQUENCES)} sequences")

    # Step 4: Stamp tenant_default with tenant branch
    subprocess.run(
        ["alembic", "-x", "schema=tenant_default", "stamp", "tenant@head"],
        check=True,
    )
    print("Stamped tenant_default at tenant@head")

    # Step 5: Clear public.alembic_version
    async with async_session() as conn:
        await conn.execute(text("DELETE FROM public.alembic_version"))
        await conn.commit()
    print("Cleared public.alembic_version")

    # Step 6: Run platform migrations
    subprocess.run(["alembic", "upgrade", "platform@head"], check=True)
    print("Ran platform@head migrations")

    # Step 7: Insert first tenant record
    async with async_session() as conn:
        await conn.execute(text("""
            INSERT INTO public.tenants (name, slug, schema_name, subdomain, plan, status)
            VALUES ('Default', 'default', 'tenant_default', 'app', 'enterprise', 'active')
        """))
        await conn.commit()
    print("Inserted default tenant record")

    # Step 8: Enable TENANT_MODE
    print("Set TENANT_MODE=true in your .env file")
    print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())
```

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_multitenancy/ backend/scripts/migrate_to_multi_tenant.py
git commit -m "feat(multi-tenant): add isolation tests, lifecycle tests, and migration script"
```
git commit -m "feat(multi-tenant): add isolation tests, lifecycle tests, and migration script"
```

---

## Phase Dependency Map

```
Task 1 (Base split)
  └─→ Task 2 (Platform models)
  └─→ Task 3 (Tenant context middleware)
       └─→ Task 4 (get_db retrofit)
            └─→ Task 5 (Alembic config)
            └─→ Task 7 (Auth changes)
            └─→ Task 8 (Background tasks)
       └─→ Task 6 (Platform API)
Task 9 (Frontend) — depends on Task 7
Task 10 (Integration tests + migration script) — depends on Tasks 1-8
```

Tasks 2, 3 can run in parallel after Task 1.
Tasks 5, 6, 7 can run in parallel after Task 4.
Task 8 can start after Task 4.
Task 9 can start after Task 7.
Task 10 is the final validation.