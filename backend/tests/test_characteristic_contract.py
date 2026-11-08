import uuid

import pytest

from app.schemas.characteristic import Characteristic, CharacteristicSourceRef
from app.schemas.fmea import GraphNodeSchema
from app.services.fmea_characteristics import source_key


def test_function_characteristics_round_trip():
    cid = str(uuid.uuid4())
    node = GraphNodeSchema.model_validate({
        "id": "sf1", "type": "ProcessStepFunction", "name": "准确贴装",
        "characteristics": [{"id": cid, "kind": "product", "name": "偏移量",
                            "specification": "≤0.05 mm"}],
    })
    saved = node.model_dump(mode="json")
    assert saved["name"] == "准确贴装"
    assert saved["characteristics"][0]["id"] == cid
    assert saved["characteristics"][0]["name"] == "偏移量"


def test_characteristic_contract_defaults_related_product_ids_to_empty_list():
    characteristic = Characteristic(
        id=uuid.uuid4(), kind="process", name="贴装压力", specification="3.0±0.5",
    )
    assert characteristic.related_product_characteristic_ids == []


def test_source_key_is_stable_without_mapping_or_accepted_version():
    ref = CharacteristicSourceRef(
        mapping_version=2,
        fmea_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        step_id="op10",
        function_id="sf1",
        work_element_id="we1",
        characteristic_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        accepted_source_version_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
    )
    assert source_key(ref) == (
        '{"characteristic_id":"22222222-2222-2222-2222-222222222222",'
        '"fmea_id":"11111111-1111-1111-1111-111111111111",'
        '"function_id":"sf1","step_id":"op10"}'
    )


def _pfmea_graph():
    product_id = str(uuid.uuid4())
    process_id = str(uuid.uuid4())
    return {
        "nodes": [
            {"id": "step-10", "type": "ProcessStep", "name": "贴装"},
            {"id": "sf-10", "type": "ProcessStepFunction", "name": "准确贴装",
             "characteristics": [{"id": product_id, "kind": "product", "name": "偏移量",
                                  "specification": "≤0.05 mm"}]},
            {"id": "we-10", "type": "ProcessWorkElement", "name": "人员操作",
             "classification": "Man"},
            {"id": "wef-10", "type": "ProcessWorkElementFunction", "name": "控制贴装压力",
             "characteristics": [{"id": process_id, "kind": "process", "name": "贴装压力",
                                  "specification": None,
                                  "related_product_characteristic_ids": [product_id]}]},
        ],
        "edges": [
            {"source": "step-10", "target": "sf-10", "type": "HAS_FUNCTION"},
            {"source": "step-10", "target": "we-10", "type": "HAS_WORK_ELEMENT"},
            {"source": "we-10", "target": "wef-10", "type": "HAS_FUNCTION"},
            {"source": "sf-10", "target": "wef-10", "type": "FUNCTION_MAPPED_TO"},
        ],
    }


def test_validate_characteristics_accepts_pfmea_document_ownership_and_empty_specification():
    from app.services.fmea_characteristics import validate_characteristics

    graph = _pfmea_graph()
    validate_characteristics("PFMEA", graph)


def test_validate_characteristics_accepts_dfmea_product_on_shared_work_element_function_type():
    from app.services.fmea_characteristics import validate_characteristics

    graph = {
        "nodes": [
            {"id": "component", "type": "Component", "name": "功率模块"},
            {"id": "shared-type", "type": "ProcessWorkElementFunction", "name": "输出稳定",
             "characteristics": [{"id": str(uuid.uuid4()), "kind": "product", "name": "输出电压"}]},
        ],
        "edges": [{"source": "component", "target": "shared-type", "type": "HAS_FUNCTION"}],
    }
    validate_characteristics("DFMEA", graph)


def test_validate_characteristics_rejects_wrong_type_for_pfmea_work_element_function():
    from app.services.fmea_characteristics import validate_characteristics

    graph = _pfmea_graph()
    graph["nodes"][3]["characteristics"][0]["kind"] = "product"
    with pytest.raises(ValueError):
        validate_characteristics("PFMEA", graph)


def test_validate_characteristics_rejects_duplicate_ids_within_one_document():
    from app.services.fmea_characteristics import validate_characteristics

    graph = _pfmea_graph()
    duplicate = dict(graph["nodes"][1]["characteristics"][0])
    graph["nodes"][1]["characteristics"].append(duplicate)
    with pytest.raises(ValueError):
        validate_characteristics("PFMEA", graph)


def test_validate_characteristics_rejects_dangling_or_cross_step_product_reference():
    from app.services.fmea_characteristics import validate_characteristics

    graph = _pfmea_graph()
    graph["nodes"][3]["characteristics"][0]["related_product_characteristic_ids"] = [str(uuid.uuid4())]
    with pytest.raises(ValueError):
        validate_characteristics("PFMEA", graph)

    graph = _pfmea_graph()
    graph["nodes"].extend([
        {"id": "step-20", "type": "ProcessStep", "name": "贴装"},
        {"id": "sf-20", "type": "ProcessStepFunction", "name": "回流完整",
         "characteristics": [{"id": str(uuid.uuid4()), "kind": "product", "name": "回流温度"}]},
    ])
    graph["edges"].append({"source": "step-20", "target": "sf-20", "type": "HAS_FUNCTION"})
    graph["nodes"][3]["characteristics"][0]["related_product_characteristic_ids"] = [
        graph["nodes"][-1]["characteristics"][0]["id"]
    ]
    with pytest.raises(ValueError):
        validate_characteristics("PFMEA", graph)


def test_validate_characteristics_keeps_legacy_missing_collection_distinct_from_empty_collection():
    from app.services.fmea_characteristics import validate_characteristics

    legacy = {"nodes": [{"id": "sf-legacy", "type": "ProcessStepFunction", "name": "旧功能"}], "edges": []}
    explicit_empty = {
        "nodes": [
            {"id": "step-empty", "type": "ProcessStep", "name": "新工序"},
            {"id": "sf-empty", "type": "ProcessStepFunction", "name": "新功能", "characteristics": []},
        ],
        "edges": [{"source": "step-empty", "target": "sf-empty", "type": "HAS_FUNCTION"}],
    }

    validate_characteristics("PFMEA", legacy)
    validate_characteristics("PFMEA", explicit_empty)
    assert "characteristics" not in legacy["nodes"][0]
    assert explicit_empty["nodes"][1]["characteristics"] == []


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_fmea_snapshots_restore_legacy_and_structured_characteristic_graphs(
    db, default_factory, admin_user,
):
    import copy

    from app.models.fmea import FMEADocument
    from app.services.fmea_service import update_fmea
    from app.services.version_service import create_fmea_version, rollback_fmea

    legacy_graph = {
        "nodes": [
            {"id": "step-10", "type": "ProcessStep", "name": "贴装", "severity": 8},
            {"id": "sf-10", "type": "ProcessStepFunction", "name": "准确贴装",
             "requirement": "偏移量受控", "occurrence": 4},
        ],
        "edges": [{"source": "step-10", "target": "sf-10", "type": "HAS_FUNCTION"}],
        "wizardScope": {"wizard_completed": True, "task": "历史图"},
    }
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-CHAR-{uuid.uuid4().hex[:6]}",
        title="特性快照", fmea_type="PFMEA", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft", created_by=admin_user.user_id,
        graph_data=copy.deepcopy(legacy_graph),
    )
    db.add(fmea)
    await db.flush()
    legacy_version = await create_fmea_version(db, fmea, "submit", "保存旧图", admin_user.user_id)

    structured_graph = copy.deepcopy(legacy_graph)
    characteristic_id = str(uuid.uuid4())
    structured_graph["nodes"][1]["characteristics"] = [{
        "id": characteristic_id, "kind": "product", "name": "偏移量",
        "specification": "≤0.05 mm", "classification": "CC",
    }]
    await update_fmea(db, fmea, title=None, graph_data=structured_graph, user_id=admin_user.user_id)
    structured_version = await create_fmea_version(db, fmea, "submit", "保存结构化特性", admin_user.user_id)

    await rollback_fmea(
        db, fmea, legacy_version.major_no, legacy_version.minor_no,
        reason="验证旧快照", user_id=admin_user.user_id,
    )
    assert fmea.graph_data["wizardScope"] == legacy_graph["wizardScope"]
    assert fmea.graph_data["nodes"][0]["severity"] == 8
    assert "characteristics" not in fmea.graph_data["nodes"][1]

    await rollback_fmea(
        db, fmea, structured_version.major_no, structured_version.minor_no,
        reason="验证结构化快照", user_id=admin_user.user_id,
    )
    assert fmea.graph_data["nodes"][1]["requirement"] == "偏移量受控"
    assert fmea.graph_data["nodes"][1]["characteristics"][0]["id"] == characteristic_id


def test_cp_response_exposes_pending_and_document_source_tracking():
    from datetime import datetime, timezone
    from app.schemas.control_plan import ControlPlanResponse

    version_id = uuid.uuid4()
    response = ControlPlanResponse.model_validate({
        "cp_id": uuid.uuid4(), "title": "CP", "document_no": "CP-T11",
        "product_line_code": "T11", "status": "draft", "version": 1,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        "sync_pending": True, "source_fmea_version_id": version_id,
    }).model_dump(mode="json")
    assert response["sync_pending"] is True
    assert response["source_fmea_version_id"] == str(version_id)
