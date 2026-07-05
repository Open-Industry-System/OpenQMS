from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CapaAIAdoption
from app.schemas.capa_verification import AdoptRequest
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
