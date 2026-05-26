import uuid
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.iqc_material import IqcMaterial
from app.models.audit import AuditLog


async def list_materials(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    product_line_code: str | None = None,
) -> tuple[list[IqcMaterial], int]:
    query = select(IqcMaterial)
    count_q = select(func.count(IqcMaterial.material_id))

    if search:
        filt = or_(
            IqcMaterial.part_no.ilike(f"%{search}%"),
            IqcMaterial.part_name.ilike(f"%{search}%"),
        )
        query = query.where(filt)
        count_q = count_q.where(filt)
    if product_line_code:
        query = query.where(IqcMaterial.product_line_code == product_line_code)
        count_q = count_q.where(IqcMaterial.product_line_code == product_line_code)

    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(
        query.order_by(IqcMaterial.part_no).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(items), total


async def get_material(db: AsyncSession, material_id: uuid.UUID) -> IqcMaterial | None:
    result = await db.execute(
        select(IqcMaterial).where(IqcMaterial.material_id == material_id)
    )
    return result.scalar_one_or_none()


async def create_material(
    db: AsyncSession,
    part_no: str,
    part_name: str,
    part_spec: str | None = None,
    material_type: str = "raw",
    default_aql: float | None = None,
    default_inspection_level: str | None = None,
    unit: str | None = None,
    product_line_code: str = "DC-DC-100",
    user_id: uuid.UUID | None = None,
) -> IqcMaterial:
    material = IqcMaterial(
        part_no=part_no,
        part_name=part_name,
        part_spec=part_spec,
        material_type=material_type,
        default_aql=default_aql,
        default_inspection_level=default_inspection_level,
        unit=unit,
        product_line_code=product_line_code,
        created_by=user_id,
    )
    db.add(material)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"物料号 '{part_no}' 已存在")

    if user_id:
        db.add(AuditLog(
            user_id=user_id,
            action="create",
            entity_type="iqc_material",
            entity_id=str(material.material_id),
            new_value={"part_no": part_no, "part_name": part_name},
        ))
    await db.commit()
    return material


async def update_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    user_id: uuid.UUID,
    **kwargs,
) -> IqcMaterial:
    material = await get_material(db, material_id)
    if not material:
        raise ValueError("物料不存在")
    old = {"part_no": material.part_no, "part_name": material.part_name}

    for key, value in kwargs.items():
        if value is not None and hasattr(material, key):
            setattr(material, key, value)

    db.add(AuditLog(
        user_id=user_id,
        action="update",
        entity_type="iqc_material",
        entity_id=str(material_id),
        old_value=old,
        new_value={"part_no": material.part_no, "part_name": material.part_name},
    ))
    await db.commit()
    return material


async def delete_material(db: AsyncSession, material_id: uuid.UUID) -> None:
    material = await get_material(db, material_id)
    if not material:
        raise ValueError("物料不存在")
    await db.delete(material)
    await db.commit()
