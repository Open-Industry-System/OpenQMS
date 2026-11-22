from dataclasses import asdict, replace
from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import Module, PermissionLevel
from app.models.factory import Factory
from app.models.iqc_inspection import IqcInspection
from app.models.iqc_material import IqcMaterial
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission
from app.models.supplier import Supplier
from app.models.user import User
from app.services.iqc_investigation_optional import (
    MATERIAL_PROJECTION,
    SUPPLIER_PROJECTION,
    read_current_material,
    read_current_supplier,
    read_inspection_history,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.requires_db]

TASK_DATE = date(2026, 11, 18)


@pytest_asyncio.fixture
async def sources(db, admin_user, default_factory):
    other_factory = Factory(id=uuid4(), code="IQC-OTHER", name="Other factory")
    db.add(other_factory)
    await db.flush()
    db.add_all([
        ProductLine(code="IQC-READ", name="Task line", factory_id=default_factory.id),
        ProductLine(code="IQC-HIDDEN", name="Another line", factory_id=default_factory.id),
        ProductLine(code="IQC-OTHER", name="Foreign line", factory_id=other_factory.id),
    ])
    supplier = Supplier(
        supplier_id=uuid4(), supplier_no="IQC-SUP", name="Current Supplier",
        short_name="Current", contact_email="private@example.invalid",
        created_by=admin_user.user_id, factory_id=default_factory.id,
    )
    different_supplier = Supplier(
        supplier_id=uuid4(), supplier_no="IQC-DIFF", name="Different", short_name="Different",
        created_by=admin_user.user_id, factory_id=default_factory.id,
    )
    material = IqcMaterial(
        material_id=uuid4(), part_no="IQC-READ-PART", part_name="Current Part", part_spec="Internal text",
        product_line_code="IQC-READ", factory_id=default_factory.id, created_by=admin_user.user_id,
    )
    db.add_all([supplier, different_supplier, material])
    await db.flush()

    def inspection(**overrides):
        values = {
            "inspection_id": uuid4(),
            "inspection_no": uuid4().hex,
            "supplier_id": supplier.supplier_id,
            "material_id": material.material_id,
            "part_no": material.part_no,
            "part_name": "Original Part",
            "product_line_code": "IQC-READ",
            "factory_id": default_factory.id,
            "inspection_date": TASK_DATE,
            "status": "judged",
            "inspection_result": "rejected",
        }
        values.update(overrides)
        row = IqcInspection(**values)
        db.add(row)
        return row

    anchor = inspection()
    scope = RequestScope(
        factory_scope=FactoryScope([default_factory.id], default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope("EXPLICIT", ["IQC-READ"]),
        user=admin_user,
    )
    await db.flush()
    return anchor, scope, supplier, different_supplier, material, other_factory, inspection


async def test_related_history_paginates_only_bound_records_in_90_calendar_days(db, sources):
    anchor, scope, _, different_supplier, _, other_factory, inspection = sources
    today = inspection()
    lower_bound = inspection(inspection_date=TASK_DATE - timedelta(days=89))
    inspection(inspection_date=TASK_DATE - timedelta(days=90))
    inspection(inspection_date=TASK_DATE + timedelta(days=1))
    inspection(inspection_date=None)
    inspection(product_line_code="IQC-HIDDEN")
    inspection(factory_id=other_factory.id, product_line_code="IQC-OTHER")
    inspection(supplier_id=different_supplier.supplier_id)
    inspection(material_id=None, part_no="OTHER-PART")
    await db.flush()

    first = await read_inspection_history(db, scope, anchor.inspection_id, task_date=TASK_DATE, limit=1)
    assert first is not None
    assert first.start == TASK_DATE - timedelta(days=89)
    assert first.end == TASK_DATE
    assert [row.source.object_id for row in first.items] == [today.inspection_id]
    assert first.next_cursor is not None
    second = await read_inspection_history(
        db, scope, anchor.inspection_id, task_date=TASK_DATE, cursor=first.next_cursor, limit=1,
    )
    assert second is not None
    assert [row.source.object_id for row in second.items] == [lower_bound.inspection_id]
    assert second.next_cursor is None


async def test_part_number_fallback_and_no_reliable_material(db, sources):
    anchor, scope, _, _, _, _, inspection = sources
    anchor.material_id = None
    expected = inspection(material_id=None, part_no=anchor.part_no)
    inspection(material_id=None, part_no=anchor.part_no + "-OTHER")
    await db.flush()

    page = await read_inspection_history(db, scope, anchor.inspection_id, task_date=TASK_DATE)
    assert page is not None
    assert [row.source.object_id for row in page.items] == [expected.inspection_id]

    anchor.part_no = None
    await db.flush()
    assert await read_inspection_history(db, scope, anchor.inspection_id, task_date=TASK_DATE) is None
    assert await read_current_material(db, scope, anchor.inspection_id) is None


async def test_current_summaries_expose_only_whitelisted_fields_and_version_changes(db, sources):
    anchor, scope, supplier, _, material, _, _ = sources
    projected_material = await read_current_material(db, scope, anchor.inspection_id)
    projected_supplier = await read_current_supplier(db, scope, anchor.inspection_id)

    assert projected_material is not None
    assert projected_material.part_name == "Current Part"
    assert set(asdict(projected_material)) == {"source", "part_no", "part_name"}
    assert projected_material.source.projection == MATERIAL_PROJECTION
    assert projected_supplier is not None
    assert projected_supplier.name == "Current Supplier"
    assert set(asdict(projected_supplier)) == {"source", "supplier_no", "name"}
    assert projected_supplier.source.projection == SUPPLIER_PROJECTION

    material.part_name = "Renamed Part"
    supplier.name = "Renamed Supplier"
    await db.flush()
    renamed_material = await read_current_material(db, scope, anchor.inspection_id)
    renamed_supplier = await read_current_supplier(db, scope, anchor.inspection_id)
    assert renamed_material is not None and renamed_material.source != projected_material.source
    assert renamed_supplier is not None and renamed_supplier.source != projected_supplier.source
    assert anchor.part_name == "Original Part"


async def test_optional_projections_fail_closed_on_scope_or_supplier_permission_loss(db, sources):
    anchor, scope, _, _, material, _, _ = sources
    other_line = replace(scope, pl_scope=ProductLineScope("EXPLICIT", ["IQC-HIDDEN"]))
    with pytest.raises(HTTPException) as denied:
        await read_inspection_history(db, other_line, anchor.inspection_id, task_date=TASK_DATE)
    assert denied.value.status_code == 403

    material.product_line_code = "IQC-HIDDEN"
    await db.flush()
    assert await read_current_material(db, scope, anchor.inspection_id) is None

    role = RoleDefinition(
        role_key="iqc_only", name_zh="仅来料检验", name_en="IQC only",
        is_system=False, is_editable=True, bypass_row_level_security=False,
        sort_order=100, is_active=True,
    )
    db.add(role)
    await db.flush()
    db.add(RolePermission(role_id=role.id, module=Module.IQC.value, permission_level=PermissionLevel.VIEW))
    read_only = User(
        user_id=uuid4(), username="iqc_only", display_name="IQC read",
        password_hash="unused", role_id=role.id, legacy_role="viewer",
        is_active=True, factory_id=anchor.factory_id,
    )
    db.add(read_only)
    await db.flush()

    iqc_only = replace(scope, user=read_only)
    assert await read_current_supplier(db, iqc_only, anchor.inspection_id) is None
    page = await read_inspection_history(db, iqc_only, anchor.inspection_id, task_date=TASK_DATE)
    assert page is not None and not page.items
