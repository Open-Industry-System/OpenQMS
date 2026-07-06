from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaAIAdoption, CapaRootCauseVerification
from app.schemas.capa_verification import AdoptRequest, VerificationCreate, VerificationUpdate
from app.services import capa_service
from app.services.embedding_outbox import enqueue_embedding

FIELD_MAP = {"d4": "d4_root_cause", "d5": "d5_correction"}


async def _find_existing_adoption(db: AsyncSession, capa, req: AdoptRequest):
    # 幂等去重 key：同 (capa, d_step, source, item_ref, adopted_text)。item_ref 是 JSONB，
    # SQLAlchemy == None 生成 IS NULL、== {} 生成 = '{}'::jsonb，与 ix_capa_ai_adoption_dedupe 的 COALESCE 收口一致
    return await db.scalar(select(CapaAIAdoption).where(
        CapaAIAdoption.capa_id == capa.report_id,
        CapaAIAdoption.d_step == req.d_step,
        CapaAIAdoption.source == req.source,
        CapaAIAdoption.adopted_text == req.adopted_text,
        CapaAIAdoption.item_ref == req.item_ref,
    ))


async def adopt_recommendation(db: AsyncSession, capa, req: AdoptRequest, user):
    field = FIELD_MAP[req.d_step]
    # 幂等：重复采纳（双击/重试/代理重发）直接返回既有 adoption，不重复追加 d-step 文本、不重复 audit
    existing = await _find_existing_adoption(db, capa, req)
    if existing is not None:
        await db.refresh(capa)
        return existing, getattr(capa, field) or ""

    # 锁 CAPA 行（FOR UPDATE），串行化并发采纳，防 lost update：
    # 两个并发采纳都读到旧 current、各自追加，后提交者覆盖前者（追加丢失）
    await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == capa.report_id).with_for_update())
    # 锁后重读 capa 字段，拿到最新值再追加
    await db.refresh(capa)
    current = getattr(capa, field) or ""
    new_value = f"{current}\n{req.adopted_text}" if current else req.adopted_text
    setattr(capa, field, new_value)
    adoption = CapaAIAdoption(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        d_step=req.d_step, adopted_text=req.adopted_text,
        source=req.source, stage_index=None, item_ref=req.item_ref,
        adopted_by=user.user_id,
    )
    db.add(adoption)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="ADOPT_RECOMMENDATION",
        changed_fields={
            "d_step": req.d_step, "source": req.source, "stage_index": None,
            "adopted_text": req.adopted_text, "item_ref": req.item_ref,
        },
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    if field in capa_service.EMBEDDING_FIELDS:
        await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code, capa.factory_id)
    try:
        await db.commit()
    except IntegrityError:
        # 并发下另一事务先插同 dedupe key（ix_capa_ai_adoption_dedupe 兜底）→ 回滚后查既有返回，幂等（不重复追加、不 500）
        await db.rollback()
        existing = await _find_existing_adoption(db, capa, req)
        if existing is None:
            raise   # 不是 dedupe index 冲突——不掩盖真实 DB 错误
        await db.refresh(capa)
        return existing, getattr(capa, field) or ""
    await db.refresh(adoption)
    return adoption, new_value


async def create_verification(db: AsyncSession, capa, req: VerificationCreate, user):
    rec = CapaRootCauseVerification(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        root_cause_text=req.root_cause_text, method=req.method, result=req.result,
        is_verified=req.is_verified, evidence_attachments=req.evidence_attachments,
        source_ref=req.source_ref,
        verified_by=user.user_id if req.is_verified else None,
        verified_at=func.now() if req.is_verified else None,
        # clock_timestamp() (per-statement wall-clock) not now() (constant within txn):
        # test fixture wraps inserts in one txn, so now() would give identical created_at
        # and break created_at DESC ordering. No-op in prod (each call is its own txn).
        created_at=func.clock_timestamp(),
    )
    db.add(rec)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="RC_VERIFY",
        changed_fields={
            "is_verified": req.is_verified, "root_cause_text": req.root_cause_text,
            "source_ref": req.source_ref,
        },
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    await db.commit()
    await db.refresh(rec)
    return rec


async def list_verifications(db: AsyncSession, capa):
    result = await db.execute(
        select(CapaRootCauseVerification)
        .where(CapaRootCauseVerification.capa_id == capa.report_id,
               CapaRootCauseVerification.factory_id == capa.factory_id)
        .order_by(CapaRootCauseVerification.created_at.desc()))
    return list(result.scalars().all())


async def update_verification(db: AsyncSession, capa, vid, req: VerificationUpdate, user):
    rec = await db.scalar(select(CapaRootCauseVerification).where(
        CapaRootCauseVerification.verification_id == vid,
        CapaRootCauseVerification.capa_id == capa.report_id,
        CapaRootCauseVerification.factory_id == capa.factory_id,
    ))
    if rec is None:
        raise LookupError("verification not found")
    # 用 exclude_unset 区分"省略"与"显式 null"：PATCH {method: null} 应清空，而非被当作省略跳过
    updates = req.model_dump(exclude_unset=True)
    if "is_verified" in updates and updates["is_verified"] != rec.is_verified:
        if updates["is_verified"]:
            rec.is_verified = True
            rec.verified_by = user.user_id
            rec.verified_at = func.now()
        else:
            rec.is_verified = False
            rec.verified_by = None
            rec.verified_at = None
    if "method" in updates:
        rec.method = updates["method"]
    if "result" in updates:
        rec.result = updates["result"]
    if "evidence_attachments" in updates:
        # 列为 NOT NULL（默认 []）：显式 null 视为清空到 []，避免 IntegrityError/500
        rec.evidence_attachments = updates["evidence_attachments"] or []
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="RC_VERIFY",
        changed_fields={"verification_id": str(vid), "is_verified": rec.is_verified,
                        "method": req.method, "result": req.result},
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    await db.commit()
    await db.refresh(rec)
    return rec
