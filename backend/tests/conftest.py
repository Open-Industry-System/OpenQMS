"""Shared pytest fixtures for backend tests.

Provides:
- db: async SQLAlchemy session (real database, rolled back after each test)
- admin_user: a persisted User with admin role
- plm_connection: a persisted PLMConnection linked to admin_user
"""
import uuid

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.plm import PLMConnection
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition
from app.models.user import User


@pytest_asyncio.fixture
async def db():
    """Yield an async session; roll back after the test for isolation."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


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
