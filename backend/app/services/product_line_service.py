import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product_line import ProductLine


async def list_product_lines(
    db: AsyncSession,
    is_active: bool | None = None,
    accessible_factory_ids: list[uuid.UUID] | None = None,
) -> list[ProductLine]:
    query = select(ProductLine).order_by(ProductLine.code)
    if is_active is not None:
        query = query.where(ProductLine.is_active == is_active)
    if accessible_factory_ids is not None:
        query = query.where(ProductLine.factory_id.in_(accessible_factory_ids))
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_product_line(db: AsyncSession, code: str) -> ProductLine | None:
    result = await db.execute(select(ProductLine).where(ProductLine.code == code))
    return result.scalar_one_or_none()


async def create_product_line(db: AsyncSession, code: str, name: str, factory_id: uuid.UUID | None = None) -> ProductLine:
    existing = await get_product_line(db, code)
    if existing:
        raise ValueError(f"产品线 '{code}' 已存在")
    pl = ProductLine(code=code, name=name, factory_id=factory_id)
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
    # Check downstream references before soft-deleting
    references = {}
    tables_to_check = [
        ('fmea_documents', 'product_line_code', "status != 'archived'"),
        ('capa_eightd', 'product_line_code', "status != 'closed'"),
        ('control_plans', 'product_line_code', "status != 'archived'"),
        ('inspection_characteristics', 'product_line', '1 = 1'),
        ('special_characteristics', 'product_line_code', "status = 'active'"),
        ('quality_goals', 'product_line_code', "status = 'active'"),
        ('audit_programs', 'product_line_code', "status != 'completed'"),
        ('management_reviews', 'product_line_code', "status NOT IN ('closed', 'cancelled')"),
        ('gauges', 'product_line_code', "status = 'active'"),
    ]
    for table, col, active_filter in tables_to_check:
        result = await db.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {col} = :code AND {active_filter}"),
            {'code': pl.code}
        )
        count = result.scalar()
        if count > 0:
            references[table] = count

    if references:
        ref_list = ', '.join(f'{t}({c})' for t, c in references.items())
        raise ValueError(f"产品线 {pl.code} 仍被以下模块引用，无法停用: {ref_list}")

    pl.is_active = False
    await db.commit()


async def validate_product_line(db: AsyncSession, code: str) -> None:
    """Raise ValueError if product_line code doesn't exist or is inactive."""
    pl = await get_product_line(db, code)
    if pl is None:
        raise ValueError(f"产品线 '{code}' 不存在")
    if not pl.is_active:
        raise ValueError(f"产品线 '{code}' 已停用")
