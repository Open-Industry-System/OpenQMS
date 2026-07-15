import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaAIAdoption, CapaRootCauseVerification
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import AdoptRequest, VerificationCreate, VerificationUpdate
from app.services import capa_service
from app.services.embedding_outbox import enqueue_embedding

FIELD_MAP = {"d4": "d4_root_cause", "d5": "d5_correction"}

_LINKAGE_SOURCE_D4 = "d4_cause"


def _linkage_audit(capa, fmea_id, node_id, source, user_id) -> AuditLog:
    return AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="FMEA_LINKAGE_CREATED",
        changed_fields={
            "capa_id": str(capa.report_id),
            "fmea_id": str(fmea_id),
            "node_id": node_id,
            "direction": "8d_to_fmea",
            "source": source,
        },
        operated_by=user_id, factory_id=capa.factory_id,
    )


async def _normalize_and_validate_source_ref(db: AsyncSession, capa, source_ref):
    """Normalize+validate D4 source_ref. Returns normalized dict or None.

    Rules (spec §4.1): only {fmea_id, cause_node_id}; fmea_id must equal capa's linked FMEA;
    same factory + product line; cause_node must be type=FailureCause in the FMEA graph.
    Raises ValueError (400) on shape/type violations, PermissionError (403) on cross-factory/PL.
    """
    if source_ref is None:
        return None
    if not isinstance(source_ref, dict):
        raise ValueError("source_ref 必须为对象")
    if set(source_ref.keys()) != {"fmea_id", "cause_node_id"}:
        raise ValueError("source_ref 只允许 fmea_id 与 cause_node_id")
    if capa.fmea_ref_id is None:
        raise ValueError("须先关联 FMEA")
    try:
        req_fmea = uuid.UUID(str(source_ref["fmea_id"]))
    except (ValueError, TypeError):
        raise ValueError("source_ref.fmea_id 非合法 UUID")
    if req_fmea != capa.fmea_ref_id:
        raise ValueError("source_ref.fmea_id 须等于已关联 FMEA")
    cause_node_id = str(source_ref["cause_node_id"]).strip()
    if not cause_node_id:
        raise ValueError("cause_node_id 不能为空")
    fmea = await db.get(FMEADocument, capa.fmea_ref_id)
    if fmea is None:
        raise LookupError("目标 FMEA 不存在")
    if fmea.factory_id != capa.factory_id:
        raise PermissionError("目标 FMEA 跨工厂")
    if fmea.product_line_code != capa.product_line_code:
        raise PermissionError("目标 FMEA 跨产品线")
    nodes = (fmea.graph_data or {}).get("nodes", [])
    if not any(n.get("id") == cause_node_id and n.get("type") == "FailureCause" for n in nodes):
        raise ValueError("cause_node_id 不存在于 FMEA 图或非 FailureCause")
    return {"fmea_id": str(capa.fmea_ref_id), "cause_node_id": cause_node_id}


def _assert_verified_has_details(method, result, evidence) -> None:
    # 已验证记录须留下现场验证细节（方法/结果/证据至少一项非空白），防空/纯空格验证记录绕过 D4 门禁
    if not ((method or "").strip() or (result or "").strip() or (evidence or [])):
        raise ValueError("已验证记录须填写验证方法、结果或证据")


async def _find_existing_adoption(db: AsyncSession, capa_id, req: AdoptRequest):
    # 幂等去重 key：同 (capa, d_step, source, item_ref, adopted_text)。item_ref 是 JSONB，
    # SQLAlchemy == None 生成 IS NULL、== {} 生成 = '{}'::jsonb，与 ix_capa_ai_adoption_dedupe 的 COALESCE 收口一致
    # 接收标量 capa_id（非 capa 对象）：rollback 会 expire capa，async 下访问 capa.report_id 会 MissingGreenlet
    return await db.scalar(select(CapaAIAdoption).where(
        CapaAIAdoption.capa_id == capa_id,
        CapaAIAdoption.d_step == req.d_step,
        CapaAIAdoption.source == req.source,
        CapaAIAdoption.adopted_text == req.adopted_text,
        CapaAIAdoption.item_ref == req.item_ref,
    ))


async def adopt_recommendation(db: AsyncSession, capa, req: AdoptRequest, user):
    field = FIELD_MAP[req.d_step]
    # 归一化 item_ref: None (省略) → {} (空 dict)。JSONB 把 Python None 存成 JSON null 而非 SQL NULL，
    # 若不归一化，pre-query 的 IS NULL 查不到刚插的 JSON null 行，重试会撞 unique index 后 re-raise 500。
    # 统一成 {} 后 insert 与 pre-query 用同一表示，幂等正确。
    if req.item_ref is None:
        req = req.model_copy(update={"item_ref": {}})
    # 幂等：重复采纳（双击/重试/代理重发）直接返回既有 adoption，不重复追加 d-step 文本、不重复 audit
    capa_id = capa.report_id  # 捕获标量，供 IntegrityError handler 在 rollback（expire capa）后使用
    existing = await _find_existing_adoption(db, capa_id, req)
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
        source=req.source, stage_index=req.stage_index, item_ref=req.item_ref,
        adopted_by=user.user_id,
    )
    db.add(adoption)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="ADOPT_RECOMMENDATION",
        changed_fields={
            "d_step": req.d_step, "source": req.source, "stage_index": req.stage_index,
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
        # rollback 会 expire capa；async 下访问 capa.report_id 会 MissingGreenlet → 用上方捕获的标量 capa_id
        await db.rollback()
        existing = await _find_existing_adoption(db, capa_id, req)
        if existing is None:
            raise   # 不是 dedupe index 冲突——不掩盖真实 DB 错误
        await db.refresh(capa)
        return existing, getattr(capa, field) or ""
    await db.refresh(adoption)
    return adoption, new_value


async def create_verification(db: AsyncSession, capa, req: VerificationCreate, user):
    conclusion = req.conclusion
    is_verified = (conclusion == "passed")
    if is_verified:
        _assert_verified_has_details(req.method, req.result, req.evidence_attachments)
    normalized_ref = await _normalize_and_validate_source_ref(db, capa, req.source_ref)
    rec = CapaRootCauseVerification(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        root_cause_text=req.root_cause_text, method=req.method, result=req.result,
        is_verified=is_verified, conclusion=conclusion,
        evidence_attachments=req.evidence_attachments, source_ref=normalized_ref,
        verified_by=user.user_id if is_verified else None,
        verified_at=func.now() if is_verified else None,
        # clock_timestamp() (per-statement wall-clock) not now() (constant within txn):
        # test fixture wraps inserts in one txn, so now() would give identical created_at
        # and break created_at DESC ordering. No-op in prod (each call is its own txn).
        created_at=func.clock_timestamp(),
    )
    db.add(rec)
    source_changed = normalized_ref is not None
    if conclusion == "passed":
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_PASSED",
            changed_fields={"root_cause_text": req.root_cause_text, "method": req.method,
                            "source_ref": normalized_ref},
            operated_by=user.user_id, factory_id=capa.factory_id,
        ))
    elif conclusion == "failed":
        # 创建即 failed（罕见，但支持）→ 递增
        # 锁后必须 refresh capa 读最新 retry_count，否则传入的 capa 对象可能缓存旧值
        await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == capa.report_id).with_for_update())
        await db.refresh(capa)  # 锁后重读最新值（同 adopt_recommendation 既有模式）
        capa.d4_retry_count = (capa.d4_retry_count or 0) + 1
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_FAILED",
            changed_fields={"root_cause_text": req.root_cause_text, "method": req.method,
                            "retry_count": capa.d4_retry_count, "source_ref": normalized_ref},
            operated_by=user.user_id, factory_id=capa.factory_id,
        ))
    else:
        # pending: source_ref change (establish) must be audited
        if source_changed:
            db.add(AuditLog(
                table_name="capa_eightd", record_id=capa.report_id,
                action="D4_VERIFICATION_UPDATED",
                changed_fields={"verification_id": None, "source_ref": normalized_ref,
                                "old_source_ref": None},
                operated_by=user.user_id, factory_id=capa.factory_id,
            ))
    if source_changed:
        db.add(_linkage_audit(capa, capa.fmea_ref_id, normalized_ref["cause_node_id"],
                              _LINKAGE_SOURCE_D4, user.user_id))
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
    # 锁 verification 行，序列化同记录并发跃迁（去重）
    rec = await db.scalar(select(CapaRootCauseVerification).where(
        CapaRootCauseVerification.verification_id == vid,
        CapaRootCauseVerification.capa_id == capa.report_id,
        CapaRootCauseVerification.factory_id == capa.factory_id,
    ).with_for_update())
    if rec is None:
        raise LookupError("verification not found")
    # 用 exclude_unset 区分"省略"与"显式 null"：PATCH {method: null} 应清空，而非被当作省略跳过
    updates = req.model_dump(exclude_unset=True)
    old_conclusion = rec.conclusion
    if "method" in updates:
        rec.method = updates["method"]
    if "result" in updates:
        rec.result = updates["result"]
    if "evidence_attachments" in updates:
        # 列为 NOT NULL（默认 []）：显式 null 视为清空到 []，避免 IntegrityError/500
        rec.evidence_attachments = updates["evidence_attachments"] or []
    old_source_ref = rec.source_ref
    source_ref_changed = False
    if "source_ref" in updates:
        new_ref = await _normalize_and_validate_source_ref(db, capa, updates["source_ref"])
        if new_ref != old_source_ref:
            rec.source_ref = new_ref
            source_ref_changed = True
    if "conclusion" in updates and updates["conclusion"] is not None:
        rec.conclusion = updates["conclusion"]
    # is_verified 派生
    rec.is_verified = (rec.conclusion == "passed")
    if rec.is_verified:
        rec.verified_by = user.user_id
        rec.verified_at = func.now()
    else:
        rec.verified_by = None
        rec.verified_at = None
    if rec.is_verified:
        _assert_verified_has_details(rec.method, rec.result, rec.evidence_attachments)
    # conclusion→failed 跃迁递增 retry_count（仅跃迁，防重复计；锁 capa 行防跨记录丢计数）
    if old_conclusion != "failed" and rec.conclusion == "failed":
        # 锁后必须 refresh capa 读最新 retry_count；不同 verification 并发失败时
        # 各 session 的 capa 可能缓存旧 retry_count=0，不 refresh 会丢失跨记录计数
        await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == capa.report_id).with_for_update())
        await db.refresh(capa)  # 锁后重读最新值（同 adopt_recommendation 既有模式）
        capa.d4_retry_count = (capa.d4_retry_count or 0) + 1
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_FAILED",
            changed_fields={"verification_id": str(vid), "method": rec.method,
                            "root_cause_text": rec.root_cause_text,
                            "retry_count": capa.d4_retry_count,
                            "source_ref": rec.source_ref},
            operated_by=user.user_id, factory_id=capa.factory_id,
        ))
    elif old_conclusion != "passed" and rec.conclusion == "passed":
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_PASSED",
            changed_fields={"verification_id": str(vid), "method": rec.method,
                            "root_cause_text": rec.root_cause_text,
                            "source_ref": rec.source_ref},
            operated_by=user.user_id, factory_id=capa.factory_id,
        ))
    if source_ref_changed:
        # Always write UPDATED for a source_ref field change (establish/change/clear).
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_UPDATED",
            changed_fields={"verification_id": str(vid), "source_ref": rec.source_ref,
                            "old_source_ref": old_source_ref},
            operated_by=user.user_id, factory_id=capa.factory_id,
        ))
        # LINKAGE only on establish/change (not clear). cleared → rec.source_ref is None.
        if rec.source_ref is not None:
            db.add(_linkage_audit(capa, capa.fmea_ref_id, rec.source_ref["cause_node_id"],
                                  _LINKAGE_SOURCE_D4, user.user_id))
    await db.commit()
    await db.refresh(rec)
    return rec
