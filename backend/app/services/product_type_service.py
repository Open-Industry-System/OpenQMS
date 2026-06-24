from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_type import ProductType


async def create_product_type(
    db: AsyncSession,
    code: str,
    name: str,
    description: str | None,
    created_by: str | None = None,
) -> ProductType:
    existing = await db.execute(select(ProductType).where(ProductType.code == code))
    if existing.scalar_one_or_none():
        raise ValueError(f"产品类型 '{code}' 已存在")
    pt = ProductType(code=code, name=name, description=description)
    db.add(pt)
    await db.commit()
    await db.refresh(pt)
    return pt


async def get_product_type(db: AsyncSession, code: str) -> ProductType | None:
    result = await db.execute(select(ProductType).where(ProductType.code == code))
    return result.scalar_one_or_none()


async def list_product_types(
    db: AsyncSession,
    is_active: bool | None = None,
) -> list[ProductType]:
    query = select(ProductType).order_by(ProductType.code)
    if is_active is not None:
        query = query.where(ProductType.is_active == is_active)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_product_type(
    db: AsyncSession,
    pt: ProductType,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> ProductType:
    if name is not None:
        pt.name = name
    if description is not None:
        pt.description = description
    if is_active is not None:
        pt.is_active = is_active
    await db.commit()
    await db.refresh(pt)
    return pt


async def delete_product_type(db: AsyncSession, pt: ProductType) -> None:
    pt.is_active = False
    await db.commit()
