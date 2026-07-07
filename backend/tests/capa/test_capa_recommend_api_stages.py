# backend/tests/capa/test_capa_recommend_api_stages.py
import uuid

import pytest

from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument

pytestmark = pytest.mark.requires_db


def _make_sample_graph():
    """Minimal PFMEA graph with a linked FailureMode/Cause for D4/D5."""
    fm_id = str(uuid.uuid4())
    cause_id = str(uuid.uuid4())
    prev_ctrl_id = str(uuid.uuid4())
    det_ctrl_id = str(uuid.uuid4())
    func_id = str(uuid.uuid4())
    return {
        "nodes": [
            {"id": func_id, "type": "ProcessStepFunction", "name": "焊接功能"},
            {"id": fm_id, "type": "FailureMode", "name": "焊接虚焊", "ap": "H"},
            {"id": cause_id, "type": "FailureCause", "name": "焊接参数偏移"},
            {"id": prev_ctrl_id, "type": "PreventionControl", "name": "焊接参数监控"},
            {"id": det_ctrl_id, "type": "DetectionControl", "name": "AOI光学检测"},
        ],
        "edges": [
            {"source": func_id, "target": fm_id, "type": "HAS_FAILURE_MODE"},
            {"source": cause_id, "target": fm_id, "type": "CAUSE_OF"},
            {"source": cause_id, "target": prev_ctrl_id, "type": "PREVENTED_BY"},
            {"source": cause_id, "target": det_ctrl_id, "type": "DETECTED_BY"},
        ],
    }


@pytest.fixture
async def capa_with_fmea(db, default_factory, admin_user):
    """Create a CAPA linked to an FMEA doc and return both."""
    graph = _make_sample_graph()
    fm_id = graph["nodes"][1]["id"]
    fmea_id = uuid.uuid4()
    fmea = FMEADocument(
        fmea_id=fmea_id,
        document_no="PFMEA-2026-STAGES",
        title="Stages Test FMEA",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        graph_data=graph,
        created_by=admin_user.user_id,
    )
    db.add(fmea)
    await db.flush()

    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no="8D-2026-STAGES",
        title="Stages Test",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="D4_ROOT_CAUSE",
        d2_description="焊接虚焊；焊接参数偏移",
        d4_root_cause="焊接参数偏移",
        fmea_ref_id=fmea_id,
        fmea_node_id=fm_id,
        created_by=admin_user.user_id,
    )
    db.add(capa)
    await db.flush()

    # Ensure app state attributes that lifespan normally sets exist.
    from app.main import app
    app.state.embedding_provider = None

    return capa, fmea


@pytest.mark.asyncio
async def test_d4_recommend_response_includes_stages(admin_client, capa_with_fmea):
    capa, _ = capa_with_fmea
    resp = await admin_client.get(
        f"/api/capa/{capa.report_id}/d4-fmea-recommendations"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "stages" in data, "D4 response must include 'stages'"
    assert "items" in data, "D4 response must include 'items'"

    stages = data["stages"]
    assert len(stages) == 12, f"expected 12 stages, got {len(stages)}"
    assert {s["index"] for s in stages} == set(range(1, 13)), "stage indexes must be 1..12"

    for item in data["items"]:
        assert "stage_index" in item, "each D4 item must carry stage_index"


@pytest.mark.asyncio
async def test_d5_recommend_response_includes_stages(admin_client, capa_with_fmea):
    capa, _ = capa_with_fmea
    resp = await admin_client.get(
        f"/api/capa/{capa.report_id}/d5-fmea-recommendations"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "stages" in data, "D5 response must include 'stages'"
    assert "existing_controls" in data, "D5 response must include 'existing_controls'"
    assert "general_suggestions" in data, "D5 response must include 'general_suggestions'"
    assert "items" not in data, "D5 response must not use top-level 'items'"

    stages = data["stages"]
    assert len(stages) == 12, f"expected 12 stages, got {len(stages)}"
    assert {s["index"] for s in stages} == set(range(1, 13)), "stage indexes must be 1..12"

    for item in data["existing_controls"]:
        assert "stage_index" in item, "each existing_control must carry stage_index"
    for item in data["general_suggestions"]:
        assert "stage_index" in item, "each general_suggestion must carry stage_index"
