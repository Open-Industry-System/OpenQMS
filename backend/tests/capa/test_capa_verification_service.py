import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaAIAdoption
from app.schemas.capa_verification import AdoptRequest
from app.services.capa_verification_service import adopt_recommendation

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, doc_no="8D-ADOPT-001", d4=None):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=doc_no, title="t",
        product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, d4_root_cause=d4, status="D4_ROOT_CAUSE",
    )
    db.add(capa); await db.flush()
    return capa


@pytest.mark.asyncio
async def test_adopt_appends_to_existing_d4(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4="已有根因A")
    req = AdoptRequest(d_step="d4", adopted_text="新根因B", source="fmea_graph",
                       item_ref={"failure_cause_node_id": "c1"})
    adoption, new_value = await adopt_recommendation(db, capa, req, admin_user)
    assert new_value == "已有根因A\n新根因B"
    await db.refresh(capa)
    assert capa.d4_root_cause == "已有根因A\n新根因B"
    rows = (await db.execute(select(CapaAIAdoption).where(CapaAIAdoption.capa_id == capa.report_id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].adopted_text == "新根因B"
    assert rows[0].source == "fmea_graph"
    assert rows[0].stage_index is None
    audits = (await db.execute(select(AuditLog).where(
        AuditLog.record_id == capa.report_id, AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert len(audits) == 1
    assert audits[0].changed_fields["source"] == "fmea_graph"


@pytest.mark.asyncio
async def test_adopt_writes_to_empty_field(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4=None)
    req = AdoptRequest(d_step="d4", adopted_text="根因B", source="rule")
    _, new_value = await adopt_recommendation(db, capa, req, admin_user)
    assert new_value == "根因B"
    await db.refresh(capa)
    assert capa.d4_root_cause == "根因B"


@pytest.mark.asyncio
async def test_adopt_d5_appends_to_d5_correction(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4="rc")
    capa.d5_correction = "措施A"; capa.status = "D5_CORRECTION"; await db.flush()
    req = AdoptRequest(d_step="d5", adopted_text="措施B", source="historical_capa")
    _, new_value = await adopt_recommendation(db, capa, req, admin_user)
    assert new_value == "措施A\n措施B"


@pytest.mark.asyncio
async def test_adopt_idempotent_same_payload_no_duplicate(db, default_factory, admin_user):
    # 双击/重试同一条推荐：第二次返回既有 adoption，不重复追加 d-step 文本、不新增行、不新增 audit
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4="rc")
    req = AdoptRequest(d_step="d4", adopted_text="根因B", source="fmea_graph",
                       item_ref={"failure_cause_node_id": "c1", "fmea_id": "f1"})
    first, v1 = await adopt_recommendation(db, capa, req, admin_user)
    second, v2 = await adopt_recommendation(db, capa, req, admin_user)
    assert second.adoption_id == first.adoption_id   # 幂等返回既有
    assert v2 == v1                                   # 字段值不再翻倍
    await db.refresh(capa)
    assert capa.d4_root_cause == "rc\n根因B"           # 只追加一次
    rows = (await db.execute(select(CapaAIAdoption).where(CapaAIAdoption.capa_id == capa.report_id))).scalars().all()
    assert len(rows) == 1                              # 仅 1 条 adoption
    audits = (await db.execute(select(AuditLog).where(
        AuditLog.record_id == capa.report_id, AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert len(audits) == 1                            # 仅 1 条 audit


@pytest.mark.asyncio
async def test_adopt_different_item_ref_not_deduped(db, default_factory, admin_user):
    # 不同 item_ref（不同推荐）应各落一条，不被幂等去重误杀
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4=None)
    req1 = AdoptRequest(d_step="d4", adopted_text="根因B", source="fmea_graph",
                         item_ref={"failure_cause_node_id": "c1", "fmea_id": "f1"})
    req2 = AdoptRequest(d_step="d4", adopted_text="根因B", source="fmea_graph",
                         item_ref={"failure_cause_node_id": "c2", "fmea_id": "f1"})
    await adopt_recommendation(db, capa, req1, admin_user)
    await adopt_recommendation(db, capa, req2, admin_user)
    rows = (await db.execute(select(CapaAIAdoption).where(CapaAIAdoption.capa_id == capa.report_id))).scalars().all()
    assert len(rows) == 2
