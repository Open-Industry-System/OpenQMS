# backend/tests/capa/test_capa_api_d4_d5.py
"""Tests for D4/D5 recommendation endpoint 422 BLOCKED behavior.

When no LLM credentials are configured, provider_adapter.build_client raises
ProviderNotConfiguredError → pc=None → pipeline returns blocked=True →
endpoint must raise HTTPException(422) with structured detail.
"""
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
        document_no="PFMEA-2026-D4D5",
        title="D4D5 Test FMEA",
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
        document_no="8D-2026-D4D5",
        title="D4D5 Test",
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


@pytest.fixture
async def capa_d5_with_fmea(db, default_factory, admin_user):
    """Create a CAPA at D5 status linked to an FMEA doc."""
    graph = _make_sample_graph()
    fm_id = graph["nodes"][1]["id"]
    fmea_id = uuid.uuid4()
    fmea = FMEADocument(
        fmea_id=fmea_id,
        document_no="PFMEA-2026-D5",
        title="D5 Test FMEA",
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
        document_no="8D-2026-D5",
        title="D5 Test",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="D5_CHOOSE_CORRECTION",
        d2_description="焊接虚焊；焊接参数偏移",
        d4_root_cause="焊接参数偏移",
        d5_correction="调整焊接参数",
        fmea_ref_id=fmea_id,
        fmea_node_id=fm_id,
        created_by=admin_user.user_id,
    )
    db.add(capa)
    await db.flush()

    from app.main import app
    app.state.embedding_provider = None

    return capa, fmea


@pytest.mark.asyncio
async def test_d4_endpoint_returns_422_blocked_when_no_llm(admin_client, capa_with_fmea):
    """D4 endpoint returns 422 with structured blocked detail when no LLM creds."""
    capa, _ = capa_with_fmea
    resp = await admin_client.get(
        f"/api/capa/{capa.report_id}/d4-fmea-recommendations"
    )
    assert resp.status_code == 422, (
        f"Expected 422 when no LLM creds, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json()["detail"]
    assert detail["blocked"] is True
    assert detail["reason"] == "LLM credentials not configured"
    assert "stages" in detail
    assert len(detail["stages"]) == 12


@pytest.mark.asyncio
async def test_d5_endpoint_returns_422_blocked_when_no_llm(admin_client, capa_d5_with_fmea):
    """D5 endpoint returns 422 with structured blocked detail when no LLM creds."""
    capa, _ = capa_d5_with_fmea
    resp = await admin_client.get(
        f"/api/capa/{capa.report_id}/d5-fmea-recommendations"
    )
    assert resp.status_code == 422, (
        f"Expected 422 when no LLM creds, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json()["detail"]
    assert detail["blocked"] is True
    assert detail["reason"] == "LLM credentials not configured"
    assert "stages" in detail
    assert len(detail["stages"]) == 12
