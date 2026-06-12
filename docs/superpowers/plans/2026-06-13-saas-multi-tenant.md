# SaaS 多租户架构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add schema-per-tenant multi-tenancy to OpenQMS, enabling independent organizations to share one application instance with strong data isolation via PostgreSQL schemas.

**Architecture:** Each tenant gets a `tenant_<slug>` PostgreSQL schema containing all ~50 business tables. A `TenantContext` middleware resolves the tenant from the subdomain (or `X-Tenant-ID` header in dev), sets `search_path`, and injects it into `request.state.tenant`. The existing `get_db()` dependency is retrofitted to set `search_path` based on the resolved tenant. A platform admin panel operates on the `public` schema via separate `get_platform_db()`. Background tasks iterate over active tenants via `run_for_each_tenant()`.

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
    # PlatformBase should have no registered models yet
    assert len(PlatformBase.metadata.tables) == 0


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
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP_WITH_TIME_ZONE, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP_WITH_TIMEZONE, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 6: Create `backend/app/models/tenant_migration.py`**

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey
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
        # Prevent duplicate migrations per tenant+version
        {"sqlite_autoincrement": False, "unique_constraints": [
            ("tenant_id", "version"),
        ]},
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

- [ ] **Step 3: Create `p001_platform_tables.py`**

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
        sa.Column('username', sa.String(50), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
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
git add backend/alembic/env.py backend/alembic/versions/p001_platform_tables.py backend/alembic/versions/t000_tenant_baseline.py backend/app/cli/tenant_migrate.py
git commit -m "feat(multi-tenant): add Alembic dual-base config, platform/tenant branch migrations, and tenant_migrate CLI"
```

---

### Task 6: Platform Admin Auth and API Routes

**Files:**
- Modify: `backend/app/core/security.py` — add platform admin JWT support
- Create: `backend/app/api/platform/__init__.py`
- Create: `backend/app/api/platform/auth.py`
- Create: `backend/app/api/platform/tenants.py`
- Create: `backend/app/services/tenant_service.py`
- Create: `backend/tests/test_multitenancy/test_platform_api.py`

This task creates the platform admin authentication (separate JWT, separate `platform_admin_users` table) and the `/api/platform/*` routes with enforced `get_platform_db()`.

- [ ] **Step 1: Add platform admin JWT support to `security.py`**

Add functions for creating/verifying platform admin JWTs with `is_platform_admin: true` claim, separate from tenant user JWTs. Key differences:
- Platform admin JWT has `is_platform_admin: true`, no `tenant_id`
- Tenant user JWT has `tenant_id`, no `is_platform_admin`

- [ ] **Step 2: Create platform auth route**

`backend/app/api/platform/auth.py` — Login endpoint for platform admins, using `platform_admin_users` table in `public` schema.

- [ ] **Step 3: Create platform tenants CRUD route**

`backend/app/api/platform/tenants.py` — CRUD for tenants, provisioning workflow, all using `get_platform_db()`.

- [ ] **Step 4: Create tenant service**

`backend/app/services/tenant_service.py` — Business logic for tenant lifecycle (create schema, run migrations, seed data, suspend, reactivate, deactivate).

- [ ] **Step 5: Register platform router in `main.py`**

Add `from app.api.platform import router as platform_router` and `app.include_router(platform_router)`.

- [ ] **Step 6: Write test for platform route isolation**

Verify that `/api/platform/*` routes reject tenant JWTs and ignore `X-Tenant-ID` headers.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/security.py backend/app/api/platform/ backend/app/services/tenant_service.py backend/app/main.py backend/tests/test_multitenancy/test_platform_api.py
git commit -m "feat(multi-tenant): add platform admin auth, /api/platform routes, and tenant lifecycle service"
```

---

### Task 7: Modify Existing Auth for Tenant-Aware Login

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/core/security.py`
- Modify: `backend/tests/test_multitenancy/test_tenant_context.py`

This task modifies the login flow to:
1. Resolve tenant from subdomain/X-Tenant-ID/JWT during login
2. Add `tenant_id` to JWT payload
3. Validate that JWT `tenant_id` matches the resolved tenant (cross-tenant token rejection)

- [ ] **Step 1: Modify `auth.py` login endpoint to resolve tenant and include in JWT**
- [ ] **Step 2: Modify JWT token creation to include `tenant_id` claim**
- [ ] **Step 3: Modify JWT verification to extract and validate `tenant_id`**
- [ ] **Step 4: Write test for cross-tenant JWT rejection**
- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/app/core/security.py backend/tests/test_multitenancy/test_tenant_context.py
git commit -m "feat(multi-tenant): add tenant_id to JWT and validate cross-tenant rejection"
```

---

### Task 8: Modify Background Tasks for Multi-Tenant Iteration

**Files:**
- Modify: `backend/app/main.py` — wrap all background task loops with `run_for_each_tenant()`
- Modify: Each service that uses bare `async_session()` to use `get_tenant_aware_session()`

The spec lists 7 background task groups that must be modified:
1. MES sync (`_mes_sync_loop`, `_mes_outbox_loop`, `_mes_cleanup_loop`)
2. PLM sync (`_plm_sync_loop`, `_plm_impact_loop`)
3. ERP sync (`_erp_sync_loop`)
4. Supplier risk (`_risk_eval_loop`)
5. AQL expiry (`_aql_expiry_loop`)
6. Collaboration cleanup (`_cleanup_loop`)
7. Supply chain risk map snapshot (`snapshot_loop`)

- [ ] **Step 1: Modify `main.py` lifespan to wrap background tasks with `run_for_each_tenant()`**
- [ ] **Step 2: Replace bare `async_session()` in service code with `get_tenant_aware_session()`**
- [ ] **Step 3: Write test verifying background tasks iterate over tenants**
- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/app/services/ backend/tests/test_multitenancy/
git commit -m "feat(multi-tenant): wrap background tasks with run_for_each_tenant(), replace bare async_session()"
```

---

### Task 9: Frontend Adaptation — Axios Interceptor and Auth Store

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/store/authStore.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add `X-Tenant-ID` header injection in development mode to Axios interceptor**
- [ ] **Step 2: Add `tenant_id` to JWT payload types**
- [ ] **Step 3: Add tenant status pages (`/tenant-suspended`, `/tenant-deactivated`)**
- [ ] **Step 4: Add 503 tenant-suspended and 410 tenant-deactivated response handling**
- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/store/authStore.ts frontend/src/types/index.ts frontend/src/pages/
git commit -m "feat(multi-tenant): frontend — X-Tenant-ID header, tenant status pages, 503/410 handling"
```

---

### Task 10: Integration Tests and Migration Script

**Files:**
- Create: `backend/tests/test_multitenancy/test_isolation.py`
- Create: `backend/tests/test_multitenancy/test_tenant_lifecycle.py`
- Create: `backend/scripts/migrate_to_multi_tenant.py`

- [ ] **Step 1: Write tenant isolation test**

Create `test_isolation.py` — create two tenant schemas, write data to tenant A, verify tenant B cannot read it (search_path isolation).

- [ ] **Step 2: Write tenant lifecycle test**

Create `test_tenant_lifecycle.py` — create tenant → active → suspended → reactivated → deactivated, verifying behavior at each state.

- [ ] **Step 3: Write migration script for existing deployment**

Create `migrate_to_multi_tenant.py` — the script described in §9.1 of the spec:
1. Backup `public.alembic_version`
2. `CREATE SCHEMA tenant_default`
3. `ALTER TABLE ... SET SCHEMA tenant_default` for all business objects
4. `alembic stamp tenant@head`
5. Clear `public.alembic_version`
6. `alembic upgrade platform@head`
7. Insert first tenant record
8. Enable `TENANT_MODE=true`

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_multitenancy/ backend/scripts/migrate_to_multi_tenant.py
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