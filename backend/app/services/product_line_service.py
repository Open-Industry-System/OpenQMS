from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product_line import ProductLine


async def list_product_lines(db: AsyncSession, is_active: bool | None = None) -> list[ProductLine]:
    query = select(ProductLine).order_by(ProductLine.code)
    if is_active is not None:
        query = query.where(ProductLine.is_active == is_active)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_product_line(db: AsyncSession, code: str) -> ProductLine | None:
    result = await db.execute(select(ProductLine).where(ProductLine.code == code))
    return result.scalar_one_or_none()


async def create_product_line(db: AsyncSession, code: str, name: str) -> ProductLine:
    pl = ProductLine(code=code, name=name)
    db.add(pl)
    await db.commit()
    await db.refresh(pl)
    return pl


async def update_product_line(db: AsyncSession, pl: ProductLine, name: str | None, is_active: bool | None) -> ProductLine:
    if name is not None:
        pl.name = name
    if is_active is not None:
        pl.is_active = is_active
    await db.commit()
    await db.refresh(pl)
    return pl


async def delete_product_line(db: AsyncSession, pl: ProductLine) -> None:
    pl.is_active = False
    await db.commit()


async def validate_product_line(db: AsyncSession, code: str) -> None:
    """Raise ValueError if product_line code doesn't exist or is inactive."""
    pl = await get_product_line(db, code)
    if pl is None:
        raise ValueError(f"产品线 '{code}' 不存在")
    if not pl.is_active:
        raise ValueError(f"产品线 '{code}' 已停用")
