import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaAIAdoption, CapaRootCauseVerification
from app.schemas.capa_verification import AdoptRequest, VerificationCreate, VerificationUpdate
from app.services.capa_verification_service import (
    adopt_recommendation, create_verification, list_verifications, update_verification,
)

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
async def test_adopt_idempotent_with_omitted_item_ref(db, default_factory, admin_user):
    # item_ref 省略 (None) 时，重复采纳应幂等返回既有，不 IntegrityError/500
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4="rc")
    req = AdoptRequest(d_step="d4", adopted_text="根因B", source="rule")  # item_ref defaults None
    first, _ = await adopt_recommendation(db, capa, req, admin_user)
    second, _ = await adopt_recommendation(db, capa, req, admin_user)
    assert second.adoption_id == first.adoption_id


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


@pytest.mark.asyncio
async def test_create_verification_is_verified_sets_verifier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    req = VerificationCreate(root_cause_text="rc", method="m", result="r", is_verified=True)
    rec = await create_verification(db, capa, req, admin_user)
    assert rec.is_verified is True
    assert rec.verified_by == admin_user.user_id
    assert rec.verified_at is not None


@pytest.mark.asyncio
async def test_create_verification_not_verified_no_verifier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    req = VerificationCreate(root_cause_text="rc", is_verified=False)
    rec = await create_verification(db, capa, req, admin_user)
    assert rec.is_verified is False
    assert rec.verified_by is None
    assert rec.verified_at is None


@pytest.mark.asyncio
async def test_update_flip_false_to_true_sets_verifier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(root_cause_text="rc", method="复测"), admin_user)
    assert rec.verified_by is None
    updated = await update_verification(db, capa, rec.verification_id,
                                        VerificationUpdate(is_verified=True), admin_user)
    assert updated.is_verified is True
    assert updated.verified_by == admin_user.user_id
    assert updated.verified_at is not None


@pytest.mark.asyncio
async def test_update_flip_true_to_false_clears_verifier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(root_cause_text="rc", method="复测", is_verified=True), admin_user)
    updated = await update_verification(db, capa, rec.verification_id,
                                        VerificationUpdate(is_verified=False), admin_user)
    assert updated.is_verified is False
    assert updated.verified_by is None
    assert updated.verified_at is None


@pytest.mark.asyncio
async def test_update_explicit_null_clears_method_and_result(db, default_factory, admin_user):
    # PATCH {method: null, result: null} 应清空，而非被当作省略跳过
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(
        root_cause_text="rc", method="千分尺", result="超差"), admin_user)
    updated = await update_verification(db, capa, rec.verification_id,
                                        VerificationUpdate(method=None, result=None), admin_user)
    assert updated.method is None
    assert updated.result is None


@pytest.mark.asyncio
async def test_update_omitted_fields_preserved(db, default_factory, admin_user):
    # PATCH 只改 method，省略的 result 应保持原值
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(
        root_cause_text="rc", method="千分尺", result="超差"), admin_user)
    updated = await update_verification(db, capa, rec.verification_id,
                                        VerificationUpdate(method="卡尺"), admin_user)
    assert updated.method == "卡尺"
    assert updated.result == "超差"


@pytest.mark.asyncio
async def test_update_null_evidence_clears_to_empty_not_integrity_error(db, default_factory, admin_user):
    # 列 NOT NULL：PATCH {evidence_attachments: null} 应清空到 []，而非 IntegrityError/500
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(
        root_cause_text="rc",
        evidence_attachments=[{"filename": "a.jpg", "size": 10}]), admin_user)
    updated = await update_verification(db, capa, rec.verification_id,
                                        VerificationUpdate(evidence_attachments=None), admin_user)
    assert updated.evidence_attachments == []


@pytest.mark.asyncio
async def test_update_other_capa_record_returns_404_lookup(db, default_factory, admin_user):
    capa_a = await _make_capa(db, default_factory.id, admin_user.user_id, doc_no="8D-A")
    capa_b = await _make_capa(db, default_factory.id, admin_user.user_id, doc_no="8D-B")
    rec_b = await create_verification(db, capa_b, VerificationCreate(root_cause_text="b"), admin_user)
    # 用 capa_a 的上下文去改 capa_b 的记录 → LookupError
    with pytest.raises(LookupError):
        await update_verification(db, capa_a, rec_b.verification_id,
                                  VerificationUpdate(is_verified=True), admin_user)


@pytest.mark.asyncio
async def test_list_verifications_desc_by_created(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await create_verification(db, capa, VerificationCreate(root_cause_text="first"), admin_user)
    await create_verification(db, capa, VerificationCreate(root_cause_text="second"), admin_user)
    items = await list_verifications(db, capa)
    assert [i.root_cause_text for i in items] == ["second", "first"]


def test_verification_create_rejects_empty_root_cause_text():
    # 防 D4 门禁被空验证记录绕过：root_cause_text 空白串必须被 schema 拒绝
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        VerificationCreate(root_cause_text="")
    with pytest.raises(ValidationError):
        VerificationCreate(root_cause_text="   ")
    # 非空（含可见字符）应通过
    VerificationCreate(root_cause_text="螺栓尺寸超差")


@pytest.mark.asyncio
async def test_create_verification_rejects_verified_without_details(db, default_factory, admin_user):
    # is_verified=True 但无 method/result/evidence → 拒绝（防空验证记录放行 D4 门禁）
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="验证方法|结果|证据"):
        await create_verification(db, capa, VerificationCreate(
            root_cause_text="rc", is_verified=True), admin_user)


@pytest.mark.asyncio
async def test_create_verification_rejects_verified_with_whitespace_only_details(db, default_factory, admin_user):
    # method="   " 纯空白也不算验证细节 → 拒绝（防绕过）
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="验证方法|结果|证据"):
        await create_verification(db, capa, VerificationCreate(
            root_cause_text="rc", method="   ", result="  ", is_verified=True), admin_user)


@pytest.mark.asyncio
async def test_update_verification_rejects_flip_to_verified_without_details(db, default_factory, admin_user):
    # 翻到 is_verified=True 但无 method/result/evidence → 拒绝
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(root_cause_text="rc", is_verified=False), admin_user)
    with pytest.raises(ValueError, match="验证方法|结果|证据"):
        await update_verification(db, capa, rec.verification_id,
                                  VerificationUpdate(is_verified=True), admin_user)
