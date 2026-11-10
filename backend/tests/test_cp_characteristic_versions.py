"""Control-plan characteristic provenance version contracts."""
from __future__ import annotations

import copy
import uuid

import pytest
from sqlalchemy import select

from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.control_plan_version import ControlPlanVersion
from app.schemas.characteristic import CharacteristicSourceRef
from app.schemas.control_plan import (
    ControlPlanItemCreate,
    ControlPlanItemResponse,
    ControlPlanUpdate,
)
from app.services.control_plan_service import update_control_plan
from app.services.diff_engine import diff_cp_items
from app.services.version_service import (
    compute_pg_jsonb_hash,
    create_cp_version,
    rollback_control_plan,
    verify_cp_version,
)


def _source_ref(*, accepted_source_version_id: uuid.UUID | None = None) -> dict:
    return CharacteristicSourceRef(
        mapping_version=1,
        fmea_id=uuid.UUID("00000000-0000-0000-0000-000000000010"),
        step_id="step-10",
        function_id="function-10",
        work_element_id="work-element-10",
        characteristic_id=uuid.UUID("00000000-0000-0000-0000-000000000020"),
        accepted_source_version_id=accepted_source_version_id,
    ).model_dump(mode="json")


def _item_snapshot(item_id: uuid.UUID, source_ref: dict | None, *, control_method: str = "measure") -> dict:
    snapshot = {
        "item_id": str(item_id),
        "step_no": "OP10",
        "process_name": "装配",
        "equipment": "压装机",
        "characteristic_no": None,
        "product_characteristic": "孔距",
        "process_characteristic": None,
        "special_class": "CC",
        "specification_tolerance": "10.0±0.1",
        "evaluation_method": None,
        "sample_size": None,
        "sample_frequency": None,
        "control_method": control_method,
        "reaction_plan": None,
        "source_fmea_node_id": "step-10",
        "sort_order": 0,
    }
    if source_ref is not None:
        snapshot["source_characteristic_ref"] = source_ref
    return snapshot


async def _make_cp(db, default_factory, admin_user) -> ControlPlan:
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-CHAR-{uuid.uuid4().hex[:8]}",
        title="特性来源版本",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
    )
    db.add(cp)
    await db.flush()
    return cp


def test_item_source_ref_is_typed_read_only_contract():
    """Removing the response provenance field would hide server-managed traceability."""
    accepted_version = uuid.UUID("00000000-0000-0000-0000-000000000030")
    source_ref = _source_ref(accepted_source_version_id=accepted_version)

    response = ControlPlanItemResponse.model_validate({
        "item_id": uuid.uuid4(),
        "source_characteristic_ref": source_ref,
    })
    forged_request = ControlPlanItemCreate.model_validate({
        "source_characteristic_ref": _source_ref(),
    })

    assert response.source_characteristic_ref == CharacteristicSourceRef.model_validate(source_ref)
    assert "source_characteristic_ref" not in forged_request.model_dump()


@pytest.mark.asyncio
async def test_snapshot_preserves_two_rows_with_one_source_and_complete_provenance(
    db, default_factory, admin_user,
):
    """Dropping provenance or deduplicating same-source rows would lose legal CP controls."""
    cp = await _make_cp(db, default_factory, admin_user)
    source_ref = _source_ref(accepted_source_version_id=uuid.uuid4())
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    db.add_all([
        ControlPlanItem(
            item_id=first_id, cp_id=cp.cp_id, factory_id=default_factory.id,
            step_no="OP10", product_characteristic="孔距", control_method="measure",
            source_fmea_node_id="step-10", source_characteristic_ref=copy.deepcopy(source_ref),
            sort_order=0,
        ),
        ControlPlanItem(
            item_id=second_id, cp_id=cp.cp_id, factory_id=default_factory.id,
            step_no="OP10", product_characteristic="孔距", control_method="verify",
            source_fmea_node_id="step-10", source_characteristic_ref=copy.deepcopy(source_ref),
            sort_order=1,
        ),
    ])
    await db.flush()

    version = await create_cp_version(db, cp, "manual", "保留双控制行", admin_user.user_id)

    assert [row["item_id"] for row in version.items_snapshot] == [str(first_id), str(second_id)]
    assert [row["source_characteristic_ref"] for row in version.items_snapshot] == [source_ref, source_ref]
    assert await verify_cp_version(db, version.version_id) is True


@pytest.mark.asyncio
async def test_rollback_old_snapshot_clears_new_provenance_without_mutating_historical_hash(
    db, default_factory, admin_user,
):
    """Legacy snapshots must clear future metadata while retaining their original hash."""
    cp = await _make_cp(db, default_factory, admin_user)
    item_id = uuid.uuid4()
    source_ref = _source_ref(accepted_source_version_id=uuid.uuid4())
    db.add(ControlPlanItem(
        item_id=item_id, cp_id=cp.cp_id, factory_id=default_factory.id,
        step_no="OP10", process_name="装配", equipment="压装机",
        product_characteristic="孔距", special_class="CC", specification_tolerance="10.0±0.1",
        control_method="measure", source_fmea_node_id="step-10",
        source_characteristic_ref=copy.deepcopy(source_ref), sort_order=0,
    ))
    await db.flush()

    old_items_snapshot = [_item_snapshot(item_id, None)]
    header_snapshot = {
        "document_no": cp.document_no, "title": cp.title, "fmea_ref_id": None,
        "product_line_code": cp.product_line_code, "status": cp.status, "phase": cp.phase,
        "part_no": None, "part_name": None, "contact_info": None, "drawing_rev": None,
        "org_factory": None, "core_group": None,
    }
    historical_hash = await compute_pg_jsonb_hash(
        db, {"header": header_snapshot, "items": old_items_snapshot},
    )
    old_version = ControlPlanVersion(
        version_id=uuid.uuid4(), cp_id=cp.cp_id, factory_id=default_factory.id,
        major_no=1, minor_no=0, header_snapshot=header_snapshot,
        items_snapshot=old_items_snapshot, sha256_hash=historical_hash,
        change_type="approve", created_by=admin_user.user_id,
    )
    db.add(old_version)
    await db.commit()
    old_snapshot_before = copy.deepcopy(old_version.items_snapshot)

    rollback = await rollback_control_plan(
        db, cp, 1, 0, "验证旧快照", admin_user.user_id,
    )
    restored = (await db.execute(select(ControlPlanItem).where(ControlPlanItem.item_id == item_id))).scalar_one()

    assert restored.source_characteristic_ref is None
    assert old_version.items_snapshot == old_snapshot_before
    assert old_version.sha256_hash == historical_hash
    assert await verify_cp_version(db, old_version.version_id) is True
    assert rollback.items_snapshot[0]["source_characteristic_ref"] is None


@pytest.mark.asyncio
async def test_generic_update_preserves_server_provenance_and_manual_rows_have_none(
    db, default_factory, admin_user,
):
    """A client-provided source field must not rebind an existing row or seed manual rows."""
    cp = await _make_cp(db, default_factory, admin_user)
    item_id = uuid.uuid4()
    source_ref = _source_ref(accepted_source_version_id=uuid.uuid4())
    db.add(ControlPlanItem(
        item_id=item_id, cp_id=cp.cp_id, factory_id=default_factory.id,
        step_no="OP10", product_characteristic="孔距", control_method="measure",
        source_fmea_node_id="step-10", source_characteristic_ref=copy.deepcopy(source_ref),
        sort_order=0,
    ))
    await db.flush()

    existing_request = ControlPlanItemCreate.model_validate({
        "item_id": str(item_id), "step_no": "OP10", "product_characteristic": "孔距修订",
        "control_method": "verify", "source_fmea_node_id": "step-10",
        "source_characteristic_ref": _source_ref(),
    })
    await update_control_plan(db, cp, ControlPlanUpdate(items=[
        existing_request,
        ControlPlanItemCreate(step_no="OP20", product_characteristic="手工特性", control_method="visual"),
    ]), admin_user.user_id)

    rows = (await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id).order_by(ControlPlanItem.sort_order)
    )).scalars().all()
    assert rows[0].item_id == item_id
    assert rows[0].source_characteristic_ref == source_ref
    assert rows[1].source_characteristic_ref is None


@pytest.mark.asyncio
async def test_generic_update_rejects_source_step_that_conflicts_with_provenance(
    db, default_factory, admin_user,
):
    """Changing the mutable legacy node id away from the provenance step must not corrupt linkage."""
    cp = await _make_cp(db, default_factory, admin_user)
    item_id = uuid.uuid4()
    source_ref = _source_ref()
    db.add(ControlPlanItem(
        item_id=item_id, cp_id=cp.cp_id, factory_id=default_factory.id,
        step_no="OP10", product_characteristic="孔距", control_method="measure",
        source_fmea_node_id="step-10", source_characteristic_ref=copy.deepcopy(source_ref),
        sort_order=0,
    ))
    await db.flush()

    conflicting = ControlPlanItemCreate(
        item_id=str(item_id), step_no="OP10", product_characteristic="孔距",
        control_method="measure", source_fmea_node_id="other-step",
    )
    with pytest.raises(ValueError, match="source_fmea_node_id"):
        await update_control_plan(
            db, cp, ControlPlanUpdate(items=[conflicting]), admin_user.user_id,
        )


def test_diff_detects_provenance_changes_for_stable_item_identity():
    """Ignoring source provenance in version comparison would conceal a traceability rebind."""
    item_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    before = [_item_snapshot(item_id, _source_ref())]
    after = [_item_snapshot(item_id, _source_ref(accepted_source_version_id=uuid.uuid4()))]

    diff = diff_cp_items(before, after)

    assert diff["added_items"] == []
    assert diff["deleted_items"] == []
    assert diff["modified_items"] == [{
        "item_id": str(item_id),
        "changes": [{
            "field": "source_characteristic_ref",
            "old": _source_ref(),
            "new": after[0]["source_characteristic_ref"],
        }],
    }]
