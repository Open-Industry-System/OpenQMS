from __future__ import annotations

from uuid import UUID

from app.services.cp_characteristic_mapping import derive_cp_items


def _nodes_by_id(graph: dict) -> dict[str, dict]:
    return {node["id"]: node for node in graph["nodes"]}


def test_main_demo_builders_keep_dcdc_characteristics_independent_and_unclassified():
    from app.seed import (
        DCDC_PLACEMENT_FORCE_CHARACTERISTIC_ID,
        DCDC_PLACEMENT_OFFSET_CHARACTERISTIC_ID,
        build_dcdc_pfmea_graph,
    )

    graph = build_dcdc_pfmea_graph()
    nodes = _nodes_by_id(graph)
    offset = nodes["psf_1"]["characteristics"]
    force = nodes["wef_1"]["characteristics"]

    assert offset == [{
        "id": str(DCDC_PLACEMENT_OFFSET_CHARACTERISTIC_ID),
        "kind": "product",
        "name": "元器件贴装偏移量",
        "specification": "≤0.05 mm（模拟演示值）",
        "classification": None,
    }]
    assert force == [{
        "id": str(DCDC_PLACEMENT_FORCE_CHARACTERISTIC_ID),
        "kind": "process",
        "name": "贴装力",
        "specification": "3.0±0.5 N（模拟演示值）",
        "classification": None,
        "related_product_characteristic_ids": [str(DCDC_PLACEMENT_OFFSET_CHARACTERISTIC_ID)],
    }]
    all_text = str(graph)
    assert "RPM" not in all_text
    assert "空载转速" not in all_text
    assert "压力" not in all_text
    assert "CC" not in all_text
    assert "SC" not in all_text


def test_main_demo_pfmea_maps_to_two_distinct_rows_with_fixed_source_identity():
    from app.seed import build_dcdc_pfmea_graph

    fmea_id = UUID("00000000-0000-0000-0000-00000000d101")
    result = derive_cp_items(
        fmea_id=fmea_id,
        fmea_type="PFMEA",
        graph=build_dcdc_pfmea_graph(),
        step_ids=("ps_1",),
    )

    assert result.issues == ()
    assert [(item.fields["product_characteristic"], item.fields["process_characteristic"])
            for item in result.items] == [
        ("元器件贴装偏移量", None),
        (None, "贴装力"),
    ]
    assert [item.fields["special_class"] for item in result.items] == [None, None]
    assert [item.source_ref.function_id for item in result.items] == ["psf_1", "wef_1"]
    assert all(item.source_ref.accepted_source_version_id is None for item in result.items)


def test_main_demo_control_plan_rows_are_complete_but_not_approved_provenance():
    from app.seed import build_dcdc_control_plan_item_data

    fmea_id = UUID("00000000-0000-0000-0000-00000000d101")
    rows = build_dcdc_control_plan_item_data(fmea_id)

    assert len(rows) == 2
    assert all(row["source_fmea_node_id"] == row["source_characteristic_ref"]["step_id"] for row in rows)
    offset, force = rows
    assert offset["product_characteristic"] == "元器件贴装偏移量"
    assert offset["process_characteristic"] is None
    assert offset["evaluation_method"] == "在线 AOI 检测元器件位置"
    assert offset["sample_size"] == "每件"
    assert offset["sample_frequency"] == "每件"
    assert "隔离本批次" in offset["reaction_plan"]
    assert force["product_characteristic"] is None
    assert force["process_characteristic"] == "贴装力"
    assert force["evaluation_method"] == "贴装设备贴装力传感器监控"
    assert force["sample_size"] == "每次贴装动作"
    assert force["sample_frequency"] == "每次贴装动作"
    assert "自上次合格确认以来产品" in force["reaction_plan"]
    assert all(row["special_class"] is None for row in rows)
    assert all(row["source_characteristic_ref"]["accepted_source_version_id"] is None for row in rows)


def test_dcdc_design_example_reuses_only_declared_demo_product_requirement():
    from app.seed import build_dcdc_design_dfmea_graph

    graph = build_dcdc_design_dfmea_graph()
    product_characteristics = [
        characteristic
        for node in graph["nodes"]
        for characteristic in node.get("characteristics", [])
    ]

    assert product_characteristics == [{
        "id": "00000000-0000-0000-0000-00000000d001",
        "kind": "product",
        "name": "元器件贴装偏移量",
        "specification": "≤0.05 mm（模拟演示值）",
        "classification": None,
        "reference": "演示需求，待确认",
    }]
    assert all(node.get("type") not in {"ProcessStep", "ProcessWorkElement"}
               for node in graph["nodes"] if node["id"] in {"d_sys_1", "d_sub_1", "d_cmp_1"})


def test_doc_gate_canonical_item_keeps_object_and_activity_separate_with_unknown_limit():
    from app.seed_e2e import build_docgate_item_canon, build_docgate_item_snapshot

    item = build_docgate_item_canon()
    snapshot = build_docgate_item_snapshot(UUID("00000000-0000-0000-0000-00000000e701"))

    assert item["product_characteristic"] == "孔径"
    assert item["process_characteristic"] == "定位销磨损量"
    assert item["evaluation_method"] == "首件定位销磨损量检测"
    assert item["specification_tolerance"] is None
    assert item["special_class"] is None
    assert snapshot["source_characteristic_ref"] is None
    assert snapshot["process_characteristic"] == item["process_characteristic"]


class _SeedResult:
    def scalar_one_or_none(self):
        return None


class _SeedDb:
    def __init__(self):
        self.added = []

    async def execute(self, _statement):
        return _SeedResult()

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


def test_dcdc_design_selection_never_falls_back_to_independent_bms_document():
    from app.seed import select_dcdc_design_fmea_id

    bms_id = UUID("00000000-0000-0000-0000-00000000b001")
    dcdc_id = UUID("00000000-0000-0000-0000-00000000d201")
    bms = type("Fmea", (), {
        "document_no": "DFMEA-2026-001", "fmea_type": "DFMEA",
        "product_line_code": "BMS-DEMO", "fmea_id": bms_id,
    })()
    dcdc = type("Fmea", (), {
        "document_no": "DFMEA-2026-002", "fmea_type": "DFMEA",
        "product_line_code": "DC-DC-100", "fmea_id": dcdc_id,
    })()

    assert select_dcdc_design_fmea_id([bms, dcdc]) == dcdc_id
    assert select_dcdc_design_fmea_id([bms]) is None


def test_demo_product_lines_include_an_active_bms_scope_with_existing_type():
    from app.seed import build_demo_product_line_data

    factory_id = UUID("00000000-0000-0000-0000-00000000f001")
    lines = build_demo_product_line_data(factory_id)

    assert next(line for line in lines if line["code"] == "BMS-DEMO") == {
        "code": "BMS-DEMO",
        "name": "BMS 独立演示产品线",
        "product_type_code": "POWER",
        "factory_id": factory_id,
        "is_active": True,
    }


async def test_apqp_constructor_receives_explicit_dcdc_design_id():
    from app.seed import seed_apqp

    db = _SeedDb()
    dcdc_dfmea_id = UUID("00000000-0000-0000-0000-00000000d201")
    await seed_apqp(
        db,
        UUID("00000000-0000-0000-0000-00000000a001"),
        UUID("00000000-0000-0000-0000-00000000e001"),
        UUID("00000000-0000-0000-0000-00000000f001"),
        UUID("00000000-0000-0000-0000-000000000001"),
        dfmea_id=dcdc_dfmea_id,
    )

    assert db.added[0].dfmea_id == dcdc_dfmea_id


async def test_demo_generated_rows_obey_source_step_and_ordinary_save_roundtrip(db, default_factory, admin_user):
    import uuid
    from sqlalchemy import select
    from app.seed import build_dcdc_control_plan_item_data
    from app.models.control_plan import ControlPlan, ControlPlanItem
    from app.schemas.control_plan import ControlPlanUpdate, ControlPlanItemCreate
    from app.services.control_plan_service import update_control_plan
    cp = ControlPlan(cp_id=uuid.uuid4(), document_no="DEMO-" + uuid.uuid4().hex[:8], title="Draft demo",
        factory_id=default_factory.id, product_line_code="DC-DC-100", status="draft", created_by=admin_user.user_id)
    db.add(cp)
    await db.flush()
    generated = build_dcdc_control_plan_item_data(uuid.uuid4())
    for data in generated:
        db.add(ControlPlanItem(cp_id=cp.cp_id, factory_id=cp.factory_id, **data))
    await db.flush()
    saved = list((await db.scalars(select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id).order_by(ControlPlanItem.sort_order))).all())
    data = [ControlPlanItemCreate(**{key: getattr(row, key) for key in ControlPlanItemCreate.model_fields}) for row in saved]
    await update_control_plan(db, cp, ControlPlanUpdate(items=data, lock_version=cp.lock_version), admin_user.user_id)
    for row in saved:
        await db.refresh(row)
        assert row.source_fmea_node_id == row.source_characteristic_ref["step_id"] == "ps_1"
        assert row.source_characteristic_ref["accepted_source_version_id"] is None
    assert cp.status == "draft" and cp.source_fmea_version_id is None
