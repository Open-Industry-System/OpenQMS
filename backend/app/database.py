from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
