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


async def _create_material_inner(
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
    """创建 IqcMaterial + AuditLog，flush 但不 commit。"""
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
    await db.flush()  # 先 flush 获取 material_id

    if user_id:
        db.add(AuditLog(
            table_name="iqc_materials",
            record_id=material.material_id,
            action="CREATE",
            changed_fields={"part_no": part_no, "part_name": part_name},
            operated_by=user_id,
        ))

    return material


async def bulk_import_materials(
    db: AsyncSession,
    rows: list[dict],
    product_line_code: str,
    user_id: uuid.UUID,
) -> "ImportResult":
    from app.utils.excel import ImportError as ExcelImportError, ImportResult, MAX_IMPORT_ROWS

    if len(rows) > MAX_IMPORT_ROWS:
        return ImportResult(0, [ExcelImportError(0, "", f"导入行数超过上限 {MAX_IMPORT_ROWS}")])

    # 预检查 DB 已存在的 part_no
    existing: set[str] = set()
    for row in rows:
        pn = row.get("part_no")
        if pn:
            r = await db.execute(select(IqcMaterial.material_id).where(IqcMaterial.part_no == pn))
            if r.scalar_one_or_none():
                existing.add(pn)

    errors = []
    seen = set()
    validated = []
    for row in rows:
        row_no = row.pop("_row")
        errs = []
        if not row.get("part_no"):
            errs.append(ExcelImportError(row_no, "part_no", "物料号为必填项"))
        if not row.get("part_name"):
            errs.append(ExcelImportError(row_no, "part_name", "名称为必填项"))
        pn = row.get("part_no")
        if pn:
            if pn in seen:
                errs.append(ExcelImportError(row_no, "part_no", f"批次内重复: {pn}"))
            if pn in existing:
                errs.append(ExcelImportError(row_no, "part_no", f"数据库已存在: {pn}"))
            seen.add(pn)
        # default_aql 类型校验（在校验阶段做，避免创建阶段 ValueError）
        if row.get("default_aql") is not None:
            try:
                float(row["default_aql"])
            except (ValueError, TypeError):
                errs.append(ExcelImportError(row_no, "default_aql", "默认AQL必须为数字"))
        if errs:
            errors.extend(errs)
        else:
            validated.append((row_no, row))

    if errors:
        return ImportResult(0, errors)

    created = []
    try:
        for row_no, row in validated:
            material = await _create_material_inner(
                db,
                part_no=row["part_no"],
                part_name=row["part_name"],
                part_spec=row.get("part_spec"),
                material_type=row.get("material_type", "raw"),
                default_aql=float(row["default_aql"]) if row.get("default_aql") is not None else None,
                default_inspection_level=row.get("default_inspection_level"),
                unit=row.get("unit"),
                product_line_code=row.get("product_line_code", product_line_code),
                user_id=user_id,
            )
            created.append(material)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return ImportResult(0, [ExcelImportError(0, "", "数据库写入冲突，请重试")])
    return ImportResult(len(created), [])


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
    material = await _create_material_inner(
        db, part_no, part_name, part_spec, material_type,
        default_aql, default_inspection_level, unit, product_line_code, user_id,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"物料号 '{part_no}' 已存在")
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

    changed = {}
    for key, new_val in kwargs.items():
        if new_val is not None and hasattr(material, key):
            old_val = getattr(material, key)
            if new_val != old_val:
                changed[key] = {"before": old_val, "after": new_val}
                setattr(material, key, new_val)

    if not changed:
        return material

    db.add(AuditLog(
        table_name="iqc_materials",
        record_id=material_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    ))
    await db.commit()
    return material


async def delete_material(db: AsyncSession, material_id: uuid.UUID, user_id: uuid.UUID) -> None:
    material = await get_material(db, material_id)
    if not material:
        raise ValueError("物料不存在")

    db.add(AuditLog(
        table_name="iqc_materials",
        record_id=material.material_id,
        action="DELETE",
        changed_fields={"part_no": material.part_no, "part_name": material.part_name},
        operated_by=user_id,
    ))
    await db.delete(material)
    await db.commit()
