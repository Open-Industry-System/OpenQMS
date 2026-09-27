from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import settings
from app.core.tenant_transaction import TenantBinding, TenantUnavailable, bind_business_transaction
from app.core.tenant_utils import current_tenant_binding, current_tenant_schema

engine = create_async_engine(settings.DATABASE_URL, echo=False)
# This public factory is for platform control-plane queries and single-tenant mode.
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class TenantSession(Session):
    """Dedicated sync session behind AsyncSession; never admits unbound work."""

    def __init__(self, *args, binding: TenantBinding | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.info["tenant_binding"] = binding


@event.listens_for(TenantSession, "after_begin")
def _bind_tenant_after_begin(session, transaction, connection):
    binding = session.info.get("tenant_binding")
    if binding is None:
        raise TenantUnavailable("tenant binding required")
    bind_business_transaction(connection, binding)


tenant_async_session = async_sessionmaker(
    engine, class_=AsyncSession, sync_session_class=TenantSession, expire_on_commit=False,
)


@event.listens_for(engine.sync_engine, "checkout")
def _reset_search_path_on_checkout(dbapi_connection, connection_record, *args):
    """Safety net: ensure search_path is reset to default on every pool checkout."""
    cursor = dbapi_connection.cursor()
    cursor.execute("RESET search_path")
    cursor.close()


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


async def get_db(request: Request):
    """Business requests require a captured tenant binding in multi-tenant mode."""
    tenant = getattr(request.state, "tenant", None)
    if settings.TENANT_MODE == "single":
        # Single-tenant business data is deliberately in public.
        binding = None
    else:
        captured = getattr(request.state, "tenant_binding", None)
        if (tenant is None or not isinstance(captured, TenantBinding)
                or captured.mode != "business"
                or captured.tenant_id != getattr(tenant, "id", None)
                or captured.schema_name != getattr(tenant, "schema_name", None)
                or captured.generation != getattr(tenant, "generation", None)):
            raise TenantUnavailable("captured tenant binding required")
        binding = captured
    schema_token = current_tenant_schema.set(binding.schema_name if binding else None)
    binding_token = current_tenant_binding.set(binding)
    try:
        factory = tenant_async_session if binding else async_session
        kwargs = {"binding": binding} if binding else {}
        async with factory(**kwargs) as session:
            try:
                yield session
            finally:
                if session.in_transaction():
                    await session.rollback()
    finally:
        current_tenant_binding.reset(binding_token)
        current_tenant_schema.reset(schema_token)


def _business_binding(tenant) -> TenantBinding:
    return TenantBinding(
        tenant_id=tenant.id, schema_name=tenant.schema_name,
        generation=tenant.generation, mode="business",
    )


async def get_platform_db():
    """Platform admin database session — forces search_path to 'public'.
    Used exclusively by /api/platform/* routes.
    """
    async with async_session() as session:
        await session.execute(text('SET search_path TO "public"'))
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()
            await session.execute(text('RESET search_path'))
            await session.close()


@asynccontextmanager
async def get_tenant_aware_session():
    """Worker business session bound to the ID/generation captured at entry."""
    binding = current_tenant_binding.get()
    if settings.TENANT_MODE != "single" and binding is None:
        raise TenantUnavailable("tenant binding required")
    factory = tenant_async_session if binding else async_session
    kwargs = {"binding": binding} if binding else {}
    async with factory(**kwargs) as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


async def run_for_each_tenant():
    """Iterate tenant DB sessions for background workers.

    Usage:
        async for tenant, db in run_for_each_tenant():
            await SomeService.do_work(db)

    TENANT_MODE=single (default / e2e): business tables live in ``public`` and
    the ``tenants`` registry is typically empty. Yield one public session so
    lifespan loops (risk_input outbox, MES, etc.) still run — otherwise they
    iterate zero rows and work sits pending forever (US-E2E-01.6 regression).

    Multi-tenant modes: yield one session per active tenant, with per-transaction
    admission and strict search_path binding.
    """
    from types import SimpleNamespace

    from app.models.tenant import Tenant  # lazy import to avoid circular

    if settings.TENANT_MODE == "single":
        # Sentinel exposes .slug / .schema_name for logger.format callers in main.py.
        public_tenant = SimpleNamespace(slug="public", schema_name="public", status="active")
        async with async_session() as db:
            try:
                yield public_tenant, db
            finally:
                if db.in_transaction():
                    await db.rollback()
                await db.close()
        return

    async with async_session() as session:
        result = await session.execute(select(Tenant).where(Tenant.status == "active"))
        tenants = result.scalars().all()

    for tenant in tenants:
        binding = _business_binding(tenant)
        schema_token = current_tenant_schema.set(binding.schema_name)
        binding_token = current_tenant_binding.set(binding)
        try:
            async with tenant_async_session(binding=binding) as db:
                try:
                    yield tenant, db
                finally:
                    if db.in_transaction():
                        await db.rollback()
        finally:
            # Async generator cleanup can occur in a different Context.
            try:
                current_tenant_binding.reset(binding_token)
                current_tenant_schema.reset(schema_token)
            except ValueError:
                current_tenant_binding.set(None)
                current_tenant_schema.set(None)