"""Factory CRUD service."""
import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.factory import Factory
from app.models.audit import AuditLog
from app.schemas.factory import FactoryCreate, FactoryUpdate


async def list_factories(
    db: AsyncSession,
    is_active: bool | None = None,
    accessible_factory_ids: list[uuid.UUID] | None = None,
) -> list[Factory]:
    query = select(Factory).order_by(Factory.code)
    if is_active is not None:
        query = query.where(Factory.is_active == is_active)
    if accessible_factory_ids is not None:
        query = query.where(Factory.id.in_(accessible_factory_ids))
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_factory(db: AsyncSession, factory_id: uuid.UUID) -> Factory:
    result = await db.execute(select(Factory).where(Factory.id == factory_id))
    factory = result.scalar_one_or_none()
    if factory is None:
        raise ValueError(f"工厂 '{factory_id}' 不存在")
    return factory


async def create_factory(db: AsyncSession, data: FactoryCreate, user_id: uuid.UUID) -> Factory:
    # Check unique code
    existing = await db.execute(select(Factory).where(Factory.code == data.code))
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"工厂编码 '{data.code}' 已存在")

    factory = Factory(code=data.code, name=data.name, location=data.location)
    db.add(factory)
    await db.flush()

    db.add(AuditLog(
        table_name="factories",
        record_id=factory.id,
        action="CREATE",
        changed_fields={"code": data.code, "name": data.name, "location": data.location},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(factory)
    return factory


async def update_factory(
    db: AsyncSession,
    factory_id: uuid.UUID,
    data: FactoryUpdate,
    user_id: uuid.UUID,
) -> Factory:
    factory = await get_factory(db, factory_id)

    changes: dict = {}
    if data.name is not None and data.name != factory.name:
        changes["name"] = data.name
        factory.name = data.name
    if data.location is not None and data.location != factory.location:
        changes["location"] = data.location
        factory.location = data.location
    if data.is_active is not None and data.is_active != factory.is_active:
        changes["is_active"] = data.is_active
        factory.is_active = data.is_active

    if changes:
        db.add(AuditLog(
            table_name="factories",
            record_id=factory.id,
            action="UPDATE",
            changed_fields=changes,
            operated_by=user_id,
        ))
        await db.commit()
        await db.refresh(factory)

    return factory


async def deactivate_factory(db: AsyncSession, factory_id: uuid.UUID, user_id: uuid.UUID) -> Factory:
    factory = await get_factory(db, factory_id)

    if not factory.is_active:
        raise ValueError(f"工厂 '{factory.code}' 已经停用")

    # Check if any product_lines reference this factory
    result = await db.execute(
        text("SELECT COUNT(*) FROM product_lines WHERE factory_id = :fid AND is_active = true"),
        {"fid": factory_id},
    )
    count = result.scalar()
    if count > 0:
        raise ValueError(f"工厂 '{factory.code}' 仍被 {count} 条活跃产品线引用，无法停用")

    factory.is_active = False
    db.add(AuditLog(
        table_name="factories",
        record_id=factory.id,
        action="UPDATE",
        changed_fields={"is_active": False},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(factory)
    return factory