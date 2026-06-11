"""Shared pytest fixtures for backend tests.

Provides:
- db: async SQLAlchemy session (real database, rolled back after each test)
- admin_user: a persisted User with admin role
- plm_connection: a persisted PLMConnection linked to admin_user
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")

import uuid

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.models.plm import PLMConnection
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition
from app.models.user import User

from sqlalchemy.pool import NullPool

# Test-scoped engine with NullPool so every session gets a fresh connection
# (avoids "another operation is in progress" cross-test contamination)
_test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
_test_session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    """Yield an async session whose commit() only flushes (test isolation).

    A real outer transaction wraps the session so all writes are visible
    within the test but rolled back on teardown.  We patch ``commit()``
    to flush-only so service code that calls ``await db.commit()`` still
    works without actually persisting data past the test boundary.
    """
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
async def admin_user(db: AsyncSession) -> User:
    """Create and return an admin user for the test.

    ProductLine and RoleDefinition are inserted idempotently -- the fixture
    succeeds even when the same rows already exist from a prior test.
    """
    # Ensure product line exists (FK dependency for PLMConnection)
    result = await db.execute(
        select(ProductLine).where(ProductLine.code == "DC-DC-100")
    )
    if result.scalar_one_or_none() is None:
        db.add(ProductLine(code="DC-DC-100", name="DC-DC-100"))
        await db.flush()

    # Ensure admin role exists (FK dependency for User)
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    if result.scalar_one_or_none() is None:
        db.add(
            RoleDefinition(
                role_key="admin",
                name_zh="管理员",
                name_en="Admin",
                is_system=True,
                is_active=True,
            )
        )
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
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def plm_connection(db: AsyncSession, admin_user: User) -> PLMConnection:
    """Create and return a PLMConnection for the test."""
    conn = PLMConnection(
        name="Test PLM Conn",
        connector_type="mock",
        config={},
        product_line_code="DC-DC-100",
        created_by=admin_user.user_id,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return conn
