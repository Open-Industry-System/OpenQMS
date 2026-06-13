import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.iqc_inspection_template import IqcInspectionTemplate, IqcTemplateItem


async def list_templates(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    material_id: uuid.UUID | None = None,
) -> tuple[list[IqcInspectionTemplate], int]:
    query = select(IqcInspectionTemplate).options(selectinload(IqcInspectionTemplate.items))
    count_q = select(func.count(IqcInspectionTemplate.template_id))

    if material_id:
        query = query.where(IqcInspectionTemplate.material_id == material_id)
        count_q = count_q.where(IqcInspectionTemplate.material_id == material_id)

    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(
        query.order_by(IqcInspectionTemplate.template_name).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(items), total


async def get_template(db: AsyncSession, template_id: uuid.UUID) -> IqcInspectionTemplate | None:
    result = await db.execute(
        select(IqcInspectionTemplate)
        .options(selectinload(IqcInspectionTemplate.items))
        .where(IqcInspectionTemplate.template_id == template_id)
    )
    return result.scalar_one_or_none()


async def get_active_template_for_material(
    db: AsyncSession, material_id: uuid.UUID
) -> IqcInspectionTemplate | None:
    result = await db.execute(
        select(IqcInspectionTemplate)
        .options(selectinload(IqcInspectionTemplate.items))
        .where(
            IqcInspectionTemplate.material_id == material_id,
            IqcInspectionTemplate.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def create_template(
    db: AsyncSession,
    template_name: str,
    material_id: uuid.UUID,
    items: list[dict],
    user_id: uuid.UUID,
) -> IqcInspectionTemplate:
    template = IqcInspectionTemplate(
        template_name=template_name,
        material_id=material_id,
        version=1,
        is_active=True,
        created_by=user_id,
    )
    db.add(template)
    await db.flush()

    for i, item_data in enumerate(items):
        db.add(IqcTemplateItem(
            template_id=template.template_id,
            sort_order=item_data.get("sort_order", i),
            category=item_data["category"],
            item_name=item_data["item_name"],
            inspection_method=item_data.get("inspection_method"),
            inspect_type=item_data.get("inspect_type", "attribute"),
            spec_upper=item_data.get("spec_upper"),
            spec_lower=item_data.get("spec_lower"),
            target_value=item_data.get("target_value"),
            unit=item_data.get("unit"),
            sample_size=item_data.get("sample_size"),
            aql_level=item_data.get("aql_level"),
        ))

    audit_log = AuditLog(
        table_name="iqc_inspection_templates",
        record_id=template.template_id,
        action="CREATE",
        changed_fields={
            "template_name": template_name,
            "version": 1,
            "material_id": str(material_id),
            "items_count": len(items),
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"创建检验模板失败: {e}")
    await db.refresh(template)
    return template


async def update_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    template_name: str,
    items: list[dict],
    user_id: uuid.UUID,
) -> IqcInspectionTemplate:
    """Creates a new version — deactivates old, creates new with version+1."""
    old = await get_template(db, template_id)
    if not old:
        raise ValueError("模板不存在")

    old.is_active = False
    new_version = old.version + 1

    new_template = IqcInspectionTemplate(
        template_name=template_name,
        material_id=old.material_id,
        version=new_version,
        is_active=True,
        created_by=user_id,
    )
    db.add(new_template)
    await db.flush()

    for i, item_data in enumerate(items):
        db.add(IqcTemplateItem(
            template_id=new_template.template_id,
            sort_order=item_data.get("sort_order", i),
            category=item_data["category"],
            item_name=item_data["item_name"],
            inspection_method=item_data.get("inspection_method"),
            inspect_type=item_data.get("inspect_type", "attribute"),
            spec_upper=item_data.get("spec_upper"),
            spec_lower=item_data.get("spec_lower"),
            target_value=item_data.get("target_value"),
            unit=item_data.get("unit"),
            sample_size=item_data.get("sample_size"),
            aql_level=item_data.get("aql_level"),
        ))

    audit_log = AuditLog(
        table_name="iqc_inspection_templates",
        record_id=template_id,
        action="UPDATE",
        changed_fields={
            "version": {"before": old.version, "after": new_version},
            "template_name": {"before": old.template_name, "after": template_name},
            "items_count": len(items),
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"更新检验模板失败: {e}")
    await db.refresh(new_template)
    return new_template


async def delete_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    template = await get_template(db, template_id)
    if not template:
        raise ValueError("模板不存在")

    audit_log = AuditLog(
        table_name="iqc_inspection_templates",
        record_id=template.template_id,
        action="DELETE",
        changed_fields={
            "template_name": template.template_name,
            "version": template.version,
        },
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.delete(template)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"删除检验模板失败: {e}")
