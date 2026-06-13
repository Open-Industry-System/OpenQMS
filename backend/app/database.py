from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.core.tenant_utils import current_tenant_schema, set_search_path_sql

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
    """Tenant-aware database session dependency.
    Sets search_path based on the resolved tenant.
    If no tenant (platform routes), search_path stays at default 'public'.
    """
    tenant = getattr(request.state, "tenant", None)
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
            await session.execute(text('RESET search_path'))
            await session.close()


@asynccontextmanager
async def get_tenant_aware_session():
    """Tenant-aware session factory for Service code.
    Reads the current tenant schema from ContextVar.
    Falls back to 'public' if no tenant context.
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
                await session.execute(text('RESET search_path'))
            await session.close()


async def run_for_each_tenant():
    """Iterate over all active tenants, setting search_path for each.
    Usage:
        async for tenant, db in run_for_each_tenant():
            await SomeService.do_work(db)
    """
    from app.models.tenant import Tenant  # lazy import to avoid circular

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
                    await db.execute(text('RESET search_path'))
                    await db.close()
        finally:
            # reset() can raise ValueError if the token was created in a
            # different Context (e.g. when an exception propagates through
            # an async generator and Python cleans up in a new context).
            try:
                current_tenant_schema.reset(token)
            except ValueError:
                current_tenant_schema.set(None)