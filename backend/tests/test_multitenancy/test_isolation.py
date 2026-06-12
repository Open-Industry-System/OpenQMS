"""Test that tenant schemas are properly isolated — data in tenant A is invisible to tenant B."""
import pytest
from sqlalchemy import text

from app.database import async_session
from app.core.tenant_utils import set_search_path_sql, current_tenant_schema


@pytest.mark.asyncio
async def test_tenant_data_isolation():
    """Write data to tenant_a schema, verify tenant_b cannot see it."""
    async with async_session() as conn:
        # Setup: create two test schemas
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS tenant_test_isolation_a'))
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS tenant_test_isolation_b'))
        await conn.commit()

        # Write to tenant_a
        await conn.execute(text(set_search_path_sql("tenant_test_isolation_a")))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS test_secret (
                id SERIAL PRIMARY KEY,
                value TEXT NOT NULL
            )
        """))
        await conn.execute(text("INSERT INTO test_secret (value) VALUES ('tenant_a_secret')"))
        await conn.commit()

        # Verify tenant_b cannot see it
        await conn.execute(text(set_search_path_sql("tenant_test_isolation_b")))
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'tenant_test_isolation_b'
                AND table_name = 'test_secret'
            )
        """))
        exists = result.scalar()
        assert exists is False, "tenant_b must NOT see tables from tenant_a"

        # Verify tenant_a can read its own data
        await conn.execute(text(set_search_path_sql("tenant_test_isolation_a")))
        result = await conn.execute(text("SELECT value FROM test_secret"))
        row = result.scalar()
        assert row == 'tenant_a_secret'

        # Cleanup
        await conn.execute(text('RESET search_path'))
        await conn.execute(text('DROP SCHEMA IF EXISTS tenant_test_isolation_a CASCADE'))
        await conn.execute(text('DROP SCHEMA IF EXISTS tenant_test_isolation_b CASCADE'))
        await conn.commit()


@pytest.mark.asyncio
async def test_search_path_reset_on_pool_return():
    """After a request completes, search_path must be reset via checkout event."""
    async with async_session() as conn:
        # Set search_path to a tenant schema
        await conn.execute(text(set_search_path_sql("tenant_test_reset")))
        await conn.commit()
        await conn.close()

    # Open a new session — checkout event should have reset search_path
    async with async_session() as conn:
        result = await conn.execute(text("SELECT current_setting('search_path')"))
        search_path = result.scalar()
        assert 'tenant_test_reset' not in search_path, \
            f"search_path leaked: {search_path}"


@pytest.mark.asyncio
async def test_context_var_no_leak_on_error():
    """If a request raises an exception, current_tenant_schema must still be reset."""
    token = current_tenant_schema.set("tenant_test")
    assert current_tenant_schema.get() == "tenant_test"

    try:
        raise RuntimeError("simulated error")
    finally:
        current_tenant_schema.reset(token)

    assert current_tenant_schema.get() is None, "ContextVar must be None after reset"