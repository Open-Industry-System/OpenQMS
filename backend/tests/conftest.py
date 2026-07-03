"""Shared pytest fixtures for backend tests.

Provides:
- db: async SQLAlchemy session (real database, rolled back after each test)
- default_factory: a persisted Factory for test isolation
- admin_user: a persisted User with admin role (linked to default_factory)
- plm_connection: a persisted PLMConnection linked to admin_user
- requires_db: marker/fixture to skip tests when database is unavailable
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.deps import RequestScope, get_current_user, get_db, get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.main import app
from app.models.factory import Factory
from app.models.plm import PLMConnection
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition
from app.models.user import User

# ── Database availability check ──────────────────────────────────────────────

_db_available: bool | None = None


async def _check_db_available() -> bool:
    """Return True if the database is reachable, False otherwise."""
    global _db_available
    if _db_available is not None:
        return _db_available
    url = os.environ.get("TEST_DATABASE_URL", settings.DATABASE_URL)
    try:
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.connect() as conn:
            await conn.execute(select(1))
        await engine.dispose()
        _db_available = True
    except Exception:
        _db_available = False
    return _db_available

# ── Resolve the effective database URL for this test run ──────────────────────
_test_db_url = os.environ.get("TEST_DATABASE_URL", settings.DATABASE_URL)

# ── Patch the production engine with NullPool to prevent event-loop attachment
# issues across test functions.  Tests that use app.database.async_session or
# get_tenant_aware_session (e.g. MES concurrency, PLM sync) must not hold
# pooled connections that outlive the event loop of the test that created them.
import app.database as _db_mod

_db_mod.engine = create_async_engine(_test_db_url, echo=False, poolclass=NullPool)
_db_mod.async_session = async_sessionmaker(_db_mod.engine, class_=AsyncSession, expire_on_commit=False)

# Test-scoped engine with NullPool so every session gets a fresh connection
# (avoids "another operation is in progress" cross-test contamination)
_test_engine = create_async_engine(_test_db_url, poolclass=NullPool)
_test_session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

# Stable UUID for the default test factory
DEFAULT_FACTORY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def pytest_configure(config):
    """Register the requires_db marker."""
    config.addinivalue_line("markers", "requires_db: mark test as requiring a live database connection")


def pytest_collection_modifyitems(config, items):
    """Skip tests marked `requires_db` when the database is not reachable.

    The `db` session fixture already skips on its own, but ASGI-client tests
    whose endpoint resolves through the real `get_db` (not the fixture session)
    would error instead of skip in a no-DB lane — this marker makes them skip
    gracefully. DB availability is checked once (cached by _check_db_available).
    """
    import asyncio

    db_available = asyncio.new_event_loop().run_until_complete(_check_db_available())
    if db_available:
        return
    skip_marker = pytest.mark.skip(reason="Database not available")
    for item in items:
        if item.get_closest_marker("requires_db"):
            item.add_marker(skip_marker)


@pytest_asyncio.fixture
async def db():
    """Yield an async session whose commit() only flushes (test isolation).

    A real outer transaction wraps the session so all writes are visible
    within the test but rolled back on teardown.  We patch ``commit()``
    to flush-only so service code that calls ``await db.commit()`` still
    works without actually persisting data past the test boundary.

    Skips the test if the database is not reachable.
    """
    if not await _check_db_available():
        pytest.skip("Database not available")
    async with _test_session_factory() as session:
        # Start an outer transaction and roll it back after the test.
        # session.begin() would commit on context exit, so we manage the
        # transaction manually to guarantee rollback.
        tx = await session.begin()
        try:
            # Make session.commit() a flush-only no-op inside the test
            async def _flush_only():
                await session.flush()

            session.commit = _flush_only
            yield session
        finally:
            if tx.is_active:
                await tx.rollback()


@pytest_asyncio.fixture
async def default_factory(db: AsyncSession) -> Factory:
    """Create and return a default factory for tests.

    Uses a stable UUID so that FK references from other fixtures are
    consistent across test runs.
    """
    result = await db.execute(
        select(Factory).where(Factory.id == DEFAULT_FACTORY_ID)
    )
    factory = result.scalar_one_or_none()
    if factory is None:
        factory = Factory(
            id=DEFAULT_FACTORY_ID,
            code="TEST",
            name="Test Factory",
        )
        db.add(factory)
        await db.flush()
    return factory


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession, default_factory: Factory) -> User:
    """Create and return an admin user for the test.

    ProductLine and RoleDefinition are inserted idempotently -- the fixture
    succeeds even when the same rows already exist from a prior test.
    """
    # Ensure product line exists (FK dependency for PLMConnection)
    result = await db.execute(
        select(ProductLine).where(ProductLine.code == "DC-DC-100")
    )
    if result.scalar_one_or_none() is None:
        db.add(ProductLine(
            code="DC-DC-100",
            name="DC-DC-100",
            factory_id=default_factory.id,
        ))
        await db.flush()

    # Ensure system roles exist (FK dependency for User). Mirrors app.seed._ROLES
    # so tests match production: admin gets bypass_row_level_security=True, and
    # all system roles are present so helpers like test_user_service._make_user
    # (which default role_key="viewer") resolve a role row on a fresh CI DB.
    role_result = await db.execute(select(RoleDefinition))
    existing_roles = {r.role_key for r in role_result.scalars().all()}
    _SYSTEM_ROLES = [
        ("admin", "系统管理员", "System Admin", True, False, True, 1),
        ("manager", "质量经理", "Quality Manager", True, True, False, 2),
        ("viewer", "只读用户", "Viewer", True, False, False, 3),
        ("customer_qe", "客户质量工程师", "Customer QE", True, True, False, 4),
        ("supplier_qe", "供应商质量工程师", "Supplier QE", True, True, False, 5),
        ("field_qe", "现场质量工程师", "Field QE", True, True, False, 6),
        ("planning_qe", "前期策划质量工程师", "Planning QE", True, True, False, 7),
    ]
    for role_key, name_zh, name_en, is_system, is_editable, bypass, sort in _SYSTEM_ROLES:
        if role_key not in existing_roles:
            db.add(RoleDefinition(
                role_key=role_key,
                name_zh=name_zh,
                name_en=name_en,
                is_system=is_system,
                is_editable=is_editable,
                bypass_row_level_security=bypass,
                sort_order=sort,
                is_active=True,
            ))
    await db.flush()

    # Fetch the persisted role to get its actual id
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one()

    user = User(
        user_id=uuid.uuid4(),
        username=f"test_admin_{uuid.uuid4().hex[:8]}",
        display_name="Test Admin",
        password_hash="hashed",
        role_id=role.id,
        legacy_role="admin",
        is_active=True,
        factory_id=default_factory.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Ensure admin role has full permission matrix (admin = level 5 on every
    # module). Migration 028 seeds this, but destructive tests that
    # Base.metadata.drop_all+create_all the shared test DB (test_apqp_service,
    # test_ppap_service, test_spc_fmea_match) wipe 028's rows mid-suite, leaving
    # subsequent admin_client tests without CAPA/FMEA/etc. VIEW permission.
    # Re-seeding here makes the fixture self-sufficient regardless of prior
    # pollution. Mirrors 028_permission_matrix admin row.
    from sqlalchemy import select as _sel

    from app.core.permissions import Module
    from app.models.role import RolePermission
    existing_perms = await db.execute(
        _sel(RolePermission.module).where(RolePermission.role_id == role.id)
    )
    have = {row[0] for row in existing_perms.all()}
    for module in Module:
        if module.value not in have:
            db.add(RolePermission(role_id=role.id, module=module.value, permission_level=5))
    await db.flush()

    return user


@pytest_asyncio.fixture
async def plm_connection(db: AsyncSession, admin_user: User, default_factory: Factory) -> PLMConnection:
    """Create and return a PLMConnection for the test."""
    conn = PLMConnection(
        name="Test PLM Conn",
        connector_type="mock",
        config={},
        product_line_code="DC-DC-100",
        created_by=admin_user.user_id,
        factory_id=default_factory.id,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return conn


def _scope_for(user, default_factory, accessible_factory_ids=None, pl_mode="ALL", pl_codes=None):
    return RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=accessible_factory_ids, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode=pl_mode, codes=pl_codes),
        user=user,
    )


@pytest_asyncio.fixture
async def admin_client(db, admin_user, default_factory):
    """ASGI client authenticated as admin. Overrides get_current_user (required by require_admin),
    get_db, and get_request_scope. Clears overrides on teardown."""
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def other_admin_user(db: AsyncSession, default_factory: Factory) -> User:
    """Another admin user in the same factory, for ownership-crossing tests."""
    result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
    role = result.scalar_one()
    user = User(
        user_id=uuid.uuid4(),
        username=f"test_other_admin_{uuid.uuid4().hex[:8]}",
        display_name="Other Test Admin",
        password_hash="hashed",
        role_id=role.id,
        legacy_role="admin",
        is_active=True,
        factory_id=default_factory.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def viewer_user(db: AsyncSession, default_factory: Factory) -> User:
    """Create a user whose role is non-admin so require_admin (permissions.py:145) raises 403.
    Mirrors admin_user (conftest.py:129) but uses a viewer RoleDefinition."""
    result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "viewer"))
    role = result.scalar_one_or_none()
    if role is None:
        role = RoleDefinition(role_key="viewer", name_zh="只读用户", name_en="Viewer", is_system=True, is_active=True)
        db.add(role)
        await db.flush()
    user = User(
        user_id=uuid.uuid4(),
        username=f"test_viewer_{uuid.uuid4().hex[:8]}",
        display_name="Test Viewer",
        password_hash="hashed",
        role_id=role.id,
        legacy_role="viewer",
        is_active=True,
        factory_id=default_factory.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def request_scope_all(admin_user, default_factory):
    return _scope_for(admin_user, default_factory, accessible_factory_ids=None)


@pytest_asyncio.fixture
async def request_scope_restricted_other_factory(admin_user, default_factory):
    other = uuid.uuid4()
    return _scope_for(admin_user, default_factory, accessible_factory_ids=[other])