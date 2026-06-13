"""Tests for multi-tenant background task iteration (run_for_each_tenant, get_tenant_aware_session)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.tenant_utils import current_tenant_schema


def _make_mock_session():
    """Build an AsyncMock that behaves like async with async_session() as s.

    async_session() returns an async_sessionmaker instance. Calling it
    produces an object used as `async with async_session() as session:`.
    We mock this by returning an AsyncMock whose __aenter__ returns itself.
    session.begin() is also mocked as an async context manager since
    get_tenant_aware_session() and run_for_each_tenant() cleanup use
    `async with session.begin():`.
    """
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    # session.in_transaction() is synchronous — MagicMock, not AsyncMock
    session.in_transaction = MagicMock(return_value=False)
    # session.begin() returns an async context manager, not a coroutine
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=begin_cm)
    return session


@pytest.mark.asyncio
async def test_run_for_each_tenant_iterates_all_active_tenants():
    """run_for_each_tenant must yield (tenant, db_session) for each active tenant."""
    from app.database import run_for_each_tenant
    from app.models.tenant import Tenant

    mock_tenants = [
        Tenant(id="t1", slug="acme", schema_name="tenant_acme", subdomain="acme", status="active"),
        Tenant(id="t2", slug="globex", schema_name="tenant_globex", subdomain="globex", status="active"),
    ]

    mock_session = _make_mock_session()
    # Make the session's execute return a result that yields our tenants
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_tenants
    mock_session.execute.return_value = mock_result

    mock_sessionmaker = MagicMock(return_value=mock_session)
    with patch("app.database.async_session", mock_sessionmaker):
        seen = []
        async for tenant, db in run_for_each_tenant():
            seen.append(tenant.slug)
            # ContextVar must be set to this tenant's schema during iteration
            assert current_tenant_schema.get() == f"tenant_{tenant.slug}"

    # After iteration, ContextVar must be None (no leak)
    assert current_tenant_schema.get() is None
    assert seen == ["acme", "globex"]


@pytest.mark.asyncio
async def test_run_for_each_tenant_resets_context_var_on_failure():
    """If processing a tenant raises, the generator must still reset the
    ContextVar in its finally block. We verify this by completing the
    iteration after catching the exception (the generator's finally
    block resets the ContextVar for each tenant, so after an exception
    the ContextVar may leak in the caller's context, but the generator
    itself is properly cleaned up).

    In production, background loops wrap run_for_each_tenant() in try/except,
    so exceptions are caught and the loop continues for the next iteration.
    Here we verify that after a full iteration cycle (even with an exception
    caught mid-way), the ContextVar is properly reset.
    """
    from app.database import run_for_each_tenant
    from app.models.tenant import Tenant

    mock_tenants = [
        Tenant(id="t1", slug="acme", schema_name="tenant_acme", subdomain="acme", status="active"),
        Tenant(id="t2", slug="globex", schema_name="tenant_globex", subdomain="globex", status="active"),
    ]

    mock_session = _make_mock_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_tenants
    mock_session.execute.return_value = mock_result

    mock_sessionmaker = MagicMock(return_value=mock_session)
    with patch("app.database.async_session", mock_sessionmaker):
        seen = []
        gen = run_for_each_tenant()
        try:
            async for tenant, db in gen:
                seen.append(tenant.slug)
                if tenant.slug == "acme":
                    # Simulate a failure for the first tenant
                    raise RuntimeError("simulated failure")
        except RuntimeError:
            pass  # Catch and continue — same pattern as production background loops
        finally:
            await gen.aclose()

    # After properly closing the generator, ContextVar must be None (no leak)
    assert current_tenant_schema.get() is None


@pytest.mark.asyncio
async def test_get_tenant_aware_session_sets_search_path():
    """get_tenant_aware_session must execute SET search_path when current_tenant_schema is set."""
    from app.database import get_tenant_aware_session

    mock_session = _make_mock_session()

    token = current_tenant_schema.set("tenant_test")
    try:
        mock_sessionmaker = MagicMock(return_value=mock_session)
        with patch("app.database.async_session", mock_sessionmaker):
            async with get_tenant_aware_session() as db:
                # SET search_path must have been called with the tenant schema.
                # SQLAlchemy text() objects don't stringify to their SQL content;
                # inspect the .text attribute instead of str(call).
                executed_sql = [
                    getattr(c.args[0], "text", "") for c in mock_session.execute.call_args_list
                ]
                assert any("tenant_test" in sql for sql in executed_sql), \
                    f"Expected SET search_path to tenant_test, got SQL: {executed_sql}"
    finally:
        current_tenant_schema.reset(token)


@pytest.mark.asyncio
async def test_get_tenant_aware_session_defaults_to_public():
    """When current_tenant_schema is None, get_tenant_aware_session must not SET search_path."""
    from app.database import get_tenant_aware_session

    mock_session = _make_mock_session()

    assert current_tenant_schema.get() is None

    mock_sessionmaker = MagicMock(return_value=mock_session)
    with patch("app.database.async_session", mock_sessionmaker):
        async with get_tenant_aware_session() as db:
            # No SET search_path should be executed when ContextVar is None.
            # SQLAlchemy text() objects don't stringify to their SQL content;
            # inspect the .text attribute instead of str(call).
            executed_sql = [
                getattr(c.args[0], "text", "") for c in mock_session.execute.call_args_list
            ]
            assert not any("search_path" in sql for sql in executed_sql), \
                f"Unexpected SET search_path when no tenant context: {executed_sql}"