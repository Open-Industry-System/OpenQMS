from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.core.factory_scope import ProductLineScope
from app.models.iqc_inspection import IqcInspection
from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement
from app.models.supplier import SupplierSCAR
from app.services.iqc_investigation_facts import (
    InvestigationNotReadable,
    read_inspection_facts,
    read_item_page,
)
from tests.test_iqc_investigation_optional import sources  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.requires_db]


async def test_fact_version_changes_on_measurement_aba_but_not_investigation_link(db, sources):
    anchor, scope, supplier, *_ = sources
    anchor.judged_at = datetime.now(UTC)
    item = IqcInspectionItem(
        item_id=uuid4(), inspection_id=anchor.inspection_id, factory_id=anchor.factory_id,
        category="dimension", item_name="diameter", inspect_type="variable",
    )
    db.add(item)
    await db.flush()
    measurement = IqcItemMeasurement(
        measurement_id=uuid4(), item_id=item.item_id, factory_id=anchor.factory_id,
        measured_value=12.14,
    )
    db.add(measurement)
    await db.flush()
    original = await read_inspection_facts(db, scope, anchor.inspection_id)
    assert original.eligible
    details = await read_item_page(db, original, anchor.inspection_id, item_id=item.item_id)
    assert details.rows[0]["measured_value"] == 12.14

    revision = original.payload["inspection_revision"]
    for value in (12.16, 12.14):
        measurement.measured_value = value
        await db.flush()
    changed = await read_inspection_facts(db, scope, anchor.inspection_id)
    assert changed.payload["inspection_revision"] == revision + 2
    assert changed.version != original.version
    with pytest.raises(InvestigationNotReadable, match="changed"):
        await read_item_page(db, original, anchor.inspection_id, item_id=item.item_id)

    scar = SupplierSCAR(
        scar_id=uuid4(), scar_no=uuid4().hex, supplier_id=supplier.supplier_id,
        source_type="iqc", source_id=anchor.inspection_id, description="Hidden",
        factory_id=anchor.factory_id, product_line_code=anchor.product_line_code,
    )
    db.add(scar)
    await db.flush()
    await db.execute(
        update(IqcInspection).where(IqcInspection.inspection_id == anchor.inspection_id)
        .values(linked_scar_id=scar.scar_id)
    )
    after_link = await read_inspection_facts(db, scope, anchor.inspection_id)
    assert after_link.version == changed.version
    assert "linked_scar_id" not in after_link.payload


async def test_reinspection_scope_and_version(db, sources):
    root, scope, _, _, _, _, new_inspection = sources
    previous = await read_inspection_facts(db, scope, root.inspection_id)
    child = new_inspection(
        parent_inspection_id=root.inspection_id, re_inspection=True,
        inspection_result="accepted",
    )
    hidden = new_inspection(
        parent_inspection_id=root.inspection_id, product_line_code="IQC-HIDDEN",
    )
    await db.flush()
    current = await read_inspection_facts(db, scope, root.inspection_id)
    assert set(current.family_ids) == {root.inspection_id, child.inspection_id}
    assert current.version != previous.version
    assert hidden.inspection_id not in current.family_ids
    assert {row["inspection_result"] for row in current.payload["family"]} == {"accepted", "rejected"}

    restricted = replace(scope, pl_scope=ProductLineScope("NONE", []))
    with pytest.raises(InvestigationNotReadable):
        await read_inspection_facts(db, restricted, root.inspection_id)
    assert await db.scalar(select(IqcInspection.inspection_result).where(
        IqcInspection.inspection_id == root.inspection_id,
    )) == "rejected"


async def test_deleted_identity_cannot_be_reused_with_the_same_uuid(db, sources):
    original, scope, _, _, _, _, add_inspection = sources
    before = await read_inspection_facts(db, scope, original.inspection_id)
    object_id, number = original.inspection_id, original.inspection_no
    await db.delete(original)
    await db.flush()
    add_inspection(
        inspection_id=object_id, inspection_no=number,
        identity_generation=original.identity_generation,
    )
    await db.flush()
    rebuilt = await read_inspection_facts(db, scope, object_id)
    assert rebuilt.payload["inspection_revision"] == before.payload["inspection_revision"]
    assert rebuilt.payload["identity_generation"] != before.payload["identity_generation"]
    assert rebuilt.version != before.version
