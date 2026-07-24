"""D4→D5 retry warning + CAPAResponse retry_count exposure (US-E2E-01.3, Task B4)."""
import uuid

import pytest
from sqlalchemy import select

from app.main import app
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.schemas.capa import AdvanceRequest
from app.services import capa_service
from app.state_machines.eightd_state import EightDState

pytestmark = pytest.mark.requires_db


async def _make_capa_at_d4(db, factory_id, user_id, doc_no, retry_count=0):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=doc_no,
        title="t",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status="D4_ROOT_CAUSE",
        d4_root_cause="参数偏移",
        d4_retry_count=retry_count,
    )
    db.add(capa)
    await db.flush()

    # verified verification matching current root cause so D4→D5 gate passes
    rec = CapaRootCauseVerification(
        verification_id=uuid.uuid4(),
        capa_id=capa.report_id,
        factory_id=factory_id,
        root_cause_text="参数偏移",
        method="measurement",
        result="复现成功",
        is_verified=True,
        conclusion="passed",
        evidence_attachments=[{"name": "x.jpg"}],
        verified_by=user_id,
    )
    db.add(rec)
    await db.flush()
    return capa


@pytest.fixture
async def capa_at_d4_with_retry3(db, default_factory, admin_user):
    return await _make_capa_at_d4(
        db, default_factory.id, admin_user.user_id,
        f"8D-D4WARN-{uuid.uuid4().hex[:6]}", retry_count=3,
    )


@pytest.fixture
async def capa_at_d4_retry1(db, default_factory, admin_user):
    return await _make_capa_at_d4(
        db, default_factory.id, admin_user.user_id,
        f"8D-D4LOW-{uuid.uuid4().hex[:6]}", retry_count=1,
    )


@pytest.fixture
async def capa_at_d5(db, default_factory, admin_user):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-D5EDGE-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        created_by=admin_user.user_id,
        status="D5_CORRECTION",
        d4_root_cause="参数偏移",
        d5_correction="调整参数",
    )
    db.add(capa)
    await db.flush()
    return capa


@pytest.mark.asyncio
async def test_advance_d4_to_d5_warns_at_threshold(admin_client, capa_at_d4_with_retry3):
    capa = capa_at_d4_with_retry3
    resp = await admin_client.post(f"/api/capa/{capa.report_id}/advance", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "warning" in body
    assert "capa" in body
    assert "建议升级处理" in (body["warning"] or "")
    assert body["capa"]["status"] == "D5_CORRECTION"
    assert body["capa"]["d4_retry_count"] == 3


@pytest.mark.asyncio
async def test_capa_response_exposes_d4_retry_count(admin_client, db, default_factory, admin_user):
    capa = await _make_capa_at_d4(
        db, default_factory.id, admin_user.user_id,
        f"8D-D4EXP-{uuid.uuid4().hex[:6]}", retry_count=0,
    )
    resp = await admin_client.get(f"/api/capa/{capa.report_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["d4_retry_count"] == 0


@pytest.mark.asyncio
async def test_advance_non_d4_edge_no_warning(admin_client, capa_at_d5):
    capa = capa_at_d5
    resp = await admin_client.post(f"/api/capa/{capa.report_id}/advance", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["warning"] is None
    assert body["capa"]["status"] == "D6_VERIFICATION"


@pytest.mark.asyncio
async def test_advance_below_threshold_no_warning(admin_client, capa_at_d4_retry1):
    capa = capa_at_d4_retry1
    resp = await admin_client.post(f"/api/capa/{capa.report_id}/advance", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["warning"] is None
    assert body["capa"]["status"] == "D5_CORRECTION"
    assert body["capa"]["d4_retry_count"] == 1


@pytest.mark.asyncio
async def test_advance_service_contract_unchanged(db, default_factory, admin_user):
    capa = await _make_capa_at_d4(
        db, default_factory.id, admin_user.user_id,
        f"8D-SVC-{uuid.uuid4().hex[:6]}", retry_count=3,
    )
    result = await capa_service.advance_capa(
        db, capa, admin_user.user_id, AdvanceRequest()
    )
    assert isinstance(result, CAPAEightD)
    assert not isinstance(result, tuple)
    assert result.status == EightDState.D5_CORRECTION.value
