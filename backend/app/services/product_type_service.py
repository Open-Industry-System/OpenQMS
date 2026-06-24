import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.product_type import ProductType


async def list_product_types(db: AsyncSession, is_active: bool | None = None) -> list[ProductType]:
    query = select(ProductType).order_by(ProductType.code)
    if is_active is not None:
        query = query.where(ProductType.is_active == is_active)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_product_type(db: AsyncSession, code: str) -> ProductType | None:
    result = await db.execute(select(ProductType).where(ProductType.code == code))
    return result.scalar_one_or_none()


async def create_product_type(
    db: AsyncSession, code: str, name: str, description: str | None, operated_by: uuid.UUID
) -> ProductType:
    existing = await get_product_type(db, code)
    if existing:
        # Audit the failed-create attempt so duplicate-code tries are traceable,
        # matching the audit completeness of successful writes.
        db.add(AuditLog(
            table_name="product_types",
            record_id=uuid.uuid4(),
            action="CREATE_FAILED",
            changed_fields={"code": code, "reason": "duplicate_code"},
            operated_by=operated_by,
        ))
        await db.commit()
        raise ValueError(f"产品类型 '{code}' 已存在")
    pt = ProductType(code=code, name=name, description=description)
    db.add(pt)
    db.add(AuditLog(
        table_name="product_types",
        record_id=uuid.uuid4(),  # string-PK table; log a generated UUID, code in changed_fields
        action="CREATE",
        changed_fields={"code": code, "name": name, "description": description},
        operated_by=operated_by,
    ))
    await db.commit()
    await db.refresh(pt)
    return pt


async def update_product_type(
    db: AsyncSession, pt: ProductType, name: str | None, description: str | None, is_active: bool | None, operated_by: uuid.UUID
) -> ProductType:
    changed: dict = {}
    if name is not None and name != pt.name:
        pt.name = name; changed["name"] = name
    if description is not None and description != pt.description:
        pt.description = description; changed["description"] = description
    if is_active is not None and is_active != pt.is_active:
        pt.is_active = is_active; changed["is_active"] = is_active
    if changed:
        db.add(AuditLog(
            table_name="product_types",
            record_id=uuid.uuid4(),
            action="UPDATE",
            changed_fields=changed,
            operated_by=operated_by,
        ))
    await db.commit()
    await db.refresh(pt)
    return pt


async def delete_product_type(db: AsyncSession, pt: ProductType, operated_by: uuid.UUID) -> None:
    # Soft-delete; refused while active product lines reference it.
    result = await db.execute(
        text("SELECT COUNT(*) FROM product_lines WHERE product_type_code = :code AND is_active = true"),
        {"code": pt.code},
    )
    if result.scalar() > 0:
        raise ValueError(f"产品类型 {pt.code} 仍被活跃产品线引用，无法停用")
    pt.is_active = False
    db.add(AuditLog(
        table_name="product_types",
        record_id=uuid.uuid4(),
        action="DEACTIVATE",
        changed_fields={"is_active": False},
        operated_by=operated_by,
    ))
    await db.commit()
