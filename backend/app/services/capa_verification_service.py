import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionLevel
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaAIAdoption, CapaRootCauseVerification
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import AdoptRequest, VerificationCreate, VerificationUpdate
from app.services import capa_service
from app.services.capa_current_access import current_capa_actor_target
from app.services.embedding_outbox import enqueue_embedding
from app.services.capa_review_guard import (
    lock_capa_parent,
    lock_current_material_write,
)

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
    # source_ref is JSON-only, so serialize creation with source deletion in
    # the same CAPA -> ProductLine -> FMEA order before inspecting its graph.
    from app.services.product_line_service import lock_candidate_scopes
    await lock_candidate_scopes(db, [(capa.factory_id, capa.product_line_code)])
    fmea = await db.scalar(
        select(FMEADocument).where(FMEADocument.fmea_id == capa.fmea_ref_id)
        .with_for_update().execution_options(populate_existing=True)
    )
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


async def _find_existing_adoption(db: AsyncSession, capa_id, req: AdoptRequest, actor_id):
    # 幂等去重 key：同 (capa, d_step, source, item_ref, adopted_text)。item_ref 是 JSONB，
    # SQLAlchemy == None 生成 IS NULL、== {} 生成 = '{}'::jsonb，与 ix_capa_ai_adoption_dedupe 的 COALESCE 收口一致
    # 接收标量 capa_id（非 capa 对象）：rollback 会 expire capa，async 下访问 capa.report_id 会 MissingGreenlet
    adoption_id = await db.scalar(select(CapaAIAdoption.adoption_id).where(
        CapaAIAdoption.capa_id == capa_id,
        CapaAIAdoption.d_step == req.d_step,
        CapaAIAdoption.source == req.source,
        CapaAIAdoption.adopted_text == req.adopted_text,
        CapaAIAdoption.item_ref == req.item_ref,
    ))
    if adoption_id is None:return None
    from app.services.capa_d4_material import authorize_root
    from app.services.capa_legacy_capture import authorize_bound_sources
    await authorize_root(db,actor_id,capa_id,PermissionLevel.EDIT)
    await authorize_bound_sources(db,actor_id,capa_id,d_step='d5')
    return await db.scalar(select(CapaAIAdoption).where(CapaAIAdoption.adoption_id==adoption_id))


async def _lock_adoption_target(db,report_id,actor_id):
    """Metadata first; body lookup follows all parent waits and live checks."""
    from app.services.capa_d4_material import authorize_root
    from app.services.capa_legacy_capture import authorize_bound_sources,lock_current_history_sources
    from app.services.capa_review_guard import assert_reviewed_material_mutable
    await authorize_root(db,actor_id,report_id,PermissionLevel.EDIT)
    await authorize_bound_sources(db,actor_id,report_id,d_step='d5')
    await db.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id==report_id).with_for_update())
    await lock_current_history_sources(db,actor_id,report_id)
    capa=await current_capa_actor_target(db,actor_id,report_id,PermissionLevel.EDIT)
    assert_reviewed_material_mutable(capa)
    return capa


async def adopt_recommendation(db: AsyncSession, capa, req: AdoptRequest, user):
    from app.services.capa_entry_switch import admit
    await current_capa_actor_target(db, user.user_id, capa.report_id, PermissionLevel.EDIT)
    await admit(db, "legacy")
    actor_id = user.user_id  # rollback expires even the persisted User PK
    # This must happen before the idempotency fast-path: returning an existing
    # adoption is still a reviewed-material write admission decision.
    capa = await _lock_adoption_target(db,capa.report_id,actor_id)
    from app.services.capa_legacy_capture import canonical_request
    req = await canonical_request(db, capa, req)
    field = FIELD_MAP[req.d_step]
    # 归一化 item_ref: None (省略) → {} (空 dict)。JSONB 把 Python None 存成 JSON null 而非 SQL NULL，
    # 若不归一化，pre-query 的 IS NULL 查不到刚插的 JSON null 行，重试会撞 unique index 后 re-raise 500。
    # 统一成 {} 后 insert 与 pre-query 用同一表示，幂等正确。
    if req.item_ref is None:
        req = req.model_copy(update={"item_ref": {}})
    # 幂等：重复采纳（双击/重试/代理重发）直接返回既有 adoption，不重复追加 d-step 文本、不重复 audit
    capa_id = capa.report_id  # 捕获标量，供 IntegrityError handler 在 rollback（expire capa）后使用
    existing = await _find_existing_adoption(db, capa_id, req, actor_id)
    if existing is not None:
        from app.services.capa_d4_material import authorize_root
        await authorize_root(db, actor_id, capa.report_id)
        await db.refresh(capa)
        await authorize_root(db, actor_id, capa.report_id)
        return existing, getattr(capa, field) or ""

    from app.services.capa_legacy_capture import require_capture
    await require_capture(db, capa, req, user)
    # The parent guard already holds the row lock and returned fresh data.
    previous = getattr(capa, field)
    current = previous or ""
    new_value = f"{current}\n{req.adopted_text}" if current else req.adopted_text
    setattr(capa, field, new_value)
    adoption = CapaAIAdoption(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        d_step=req.d_step, adopted_text=req.adopted_text,
        source=req.source, stage_index=req.stage_index, item_ref=req.item_ref,
        adopted_by=actor_id,
    )
    db.add(adoption)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="ADOPT_RECOMMENDATION",
        changed_fields={
            "d_step": req.d_step, "source": req.source, "stage_index": req.stage_index,
            "adopted_text": {"changed": True} if req.d_step == "d4" or req.capture_id is not None else req.adopted_text, "item_ref": req.item_ref,
        },
        operated_by=actor_id, factory_id=capa.factory_id,
    ))
    if field in capa_service.EMBEDDING_FIELDS:
        await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code, capa.factory_id)
    try:
        if field == "d4_root_cause" and new_value != previous:
            from app.services.capa_d4_provenance import record_root_revision
            await record_root_revision(db, report_id=capa.report_id, actor_id=actor_id, write_path="capa.adopt")
        else:
            from app.services.capa_d4_material import bump_material
            await bump_material(db, capa.report_id)
        from app.services.capa_d4_material import authorize_root
        await authorize_root(db, actor_id, capa.report_id, PermissionLevel.EDIT)
        await db.commit()
    except IntegrityError:
        # 并发下另一事务先插同 dedupe key（ix_capa_ai_adoption_dedupe 兜底）→ 回滚后查既有返回，幂等（不重复追加、不 500）
        # rollback 会 expire capa；async 下访问 capa.report_id 会 MissingGreenlet → 用上方捕获的标量 capa_id
        await db.rollback()
        # A rollback ended the admission transaction and released its shared
        # drain lock. Reauthorize and re-admit before any history/body lookup
        # or parent lock in this new transaction; a crossed cutover is 410.
        from app.services.capa_d4_material import authorize_root
        from app.services.capa_legacy_capture import authorize_bound_sources
        await authorize_root(db,actor_id,capa_id,PermissionLevel.EDIT)
        await authorize_bound_sources(db,actor_id,capa_id,d_step='d5')
        await admit(db, "legacy")
        capa = await _lock_adoption_target(db,capa_id,actor_id)
        existing = await _find_existing_adoption(db, capa_id, req, actor_id)
        if existing is None:
            raise   # 不是 dedupe index 冲突——不掩盖真实 DB 错误
        await authorize_root(db,actor_id,capa_id,PermissionLevel.EDIT)
        await authorize_bound_sources(db,actor_id,capa_id,d_step='d5')
        return existing, getattr(capa, field) or ""
    from app.services.capa_d4_material import authorize_root
    await authorize_root(db, actor_id, capa.report_id)
    await db.refresh(adoption)
    await authorize_root(db, actor_id, capa.report_id)
    return adoption, new_value


async def create_verification(db: AsyncSession, capa, req: VerificationCreate, user, *, request=None):
    from app.services import capa_d4_provenance as provenance
    if req.source_declaration is not None:
        provenance.require_declaration_context(request)
    actor_id = user.user_id
    capa = await lock_current_material_write(
        db, capa, actor_id, PermissionLevel.EDIT
    )
    conclusion = req.conclusion
    is_verified = (conclusion == "passed")
    if is_verified:
        _assert_verified_has_details(req.method, req.result, req.evidence_attachments)
    await _require_verification_source_ref(db, actor_id, req.source_ref)
    if req.source_declaration is None:
        normalized_ref = await _normalize_and_validate_source_ref(db, capa, req.source_ref)
    else:
        normalized_ref, _ = await provenance.validate_declared_source(db, report=capa, actor_id=actor_id,
            source_ref=req.source_ref, conclusion=conclusion)
        try:
            await provenance.checked_current_revision(db, capa)
        except provenance.SourceRevisionConflict:
            await provenance.require_declared_source_visibility(db, capa, actor_id, normalized_ref)
            raise
    if normalized_ref is not None:
        # Source locks may have waited after parent-lock admission.
        capa = await current_capa_actor_target(db, actor_id, capa.report_id, PermissionLevel.EDIT)
    from app.services.agent_runtime.control_authority_fence import lock_employee_acl
    await lock_employee_acl(db, (actor_id,))
    await _require_verification_source_ref(db, actor_id, normalized_ref)
    capa = await current_capa_actor_target(db, actor_id, capa.report_id, PermissionLevel.EDIT)
    # Pre-generate PK so pending UPDATED audit can reference verification_id
    # before commit (model default would only fire on flush otherwise).
    vid = uuid.uuid4()
    rec = CapaRootCauseVerification(
        verification_id=vid,
        capa_id=capa.report_id, factory_id=capa.factory_id,
        root_cause_text=req.root_cause_text, method=req.method, result=req.result,
        is_verified=is_verified, conclusion=conclusion,
        evidence_attachments=req.evidence_attachments, source_ref=normalized_ref,
        verified_by=actor_id if is_verified else None,
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
            changed_fields={"verification_id": str(vid),
                            "root_cause_text": {"changed": True}, "method": req.method,
                            "source_ref": normalized_ref},
            operated_by=actor_id, factory_id=capa.factory_id,
        ))
    elif conclusion == "failed":
        # 创建即 failed（罕见，但支持）→ 递增
        capa.d4_retry_count = (capa.d4_retry_count or 0) + 1
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_FAILED",
            changed_fields={"verification_id": str(vid),
                            "root_cause_text": {"changed": True}, "method": req.method,
                            "retry_count": capa.d4_retry_count, "source_ref": normalized_ref},
            operated_by=actor_id, factory_id=capa.factory_id,
        ))
    else:
        # pending: source_ref change (establish) must be audited
        if source_changed:
            db.add(AuditLog(
                table_name="capa_eightd", record_id=capa.report_id,
                action="D4_VERIFICATION_UPDATED",
                changed_fields={"verification_id": str(vid), "source_ref": normalized_ref,
                                "old_source_ref": None},
                operated_by=actor_id, factory_id=capa.factory_id,
            ))
    if source_changed:
        db.add(_linkage_audit(capa, capa.fmea_ref_id, normalized_ref["cause_node_id"],
                              _LINKAGE_SOURCE_D4, actor_id))
    issued = False
    if req.source_declaration is not None:
        try:
            await db.flush()
            await db.refresh(rec)
            issued = await provenance.issue_source_proof(db, report=capa, verification=rec,
                actor_id=actor_id, declaration=req.source_declaration) is not None
        except Exception:
            await db.rollback()
            raise
    from app.services.capa_d4_material import bump_material, authorize_root
    await authorize_root(db, actor_id, capa.report_id, PermissionLevel.EDIT)
    await _require_original_verification_sources(db, capa.report_id, actor_id, vid)
    await bump_material(db, capa.report_id)
    await db.commit()
    await authorize_root(db, actor_id, capa.report_id)
    await _require_original_verification_sources(db, capa.report_id, actor_id, vid)
    await db.refresh(rec)
    await authorize_root(db, actor_id, capa.report_id)
    await _require_original_verification_sources(db, capa.report_id, actor_id, vid)
    rec.source_proof_issued = issued
    return rec


async def _require_original_verification_sources(db, capa_id, actor_id, verification_id=None, *, lock=False):
    from app.services.capa_verification_sources import authorize_verifications
    return await authorize_verifications(db, capa_id, actor_id=actor_id, verification_id=verification_id, lock=lock)


async def _require_verification_source_ref(db, actor_id, ref):
    if ref is None:
        return
    from types import SimpleNamespace
    from app.services.fmea_agent_sources import visible_fmea_source
    if actor_id is None or not isinstance(ref, dict) or set(ref) != {'fmea_id', 'cause_node_id'}:
        raise PermissionError('Verification source unavailable')
    try:
        source_id = uuid.UUID(str(ref['fmea_id']))
    except (ValueError, TypeError):
        raise PermissionError('Verification source unavailable') from None
    await visible_fmea_source(db, SimpleNamespace(user=SimpleNamespace(user_id=actor_id)), source_id)


async def list_verifications(db: AsyncSession, capa, *, actor_id=None):
    from app.services.capa_d4_material import root_metadata, authorize_root
    _, sources = await root_metadata(db, capa.report_id)
    if sources and actor_id is None:
        raise PermissionError('D4_MATERIAL_UNAVAILABLE')
    if actor_id is not None:
        await authorize_root(db, actor_id, capa.report_id)
    await _require_original_verification_sources(db, capa.report_id, actor_id)
    result = await db.execute(
        select(CapaRootCauseVerification)
        .where(CapaRootCauseVerification.capa_id == capa.report_id,
               CapaRootCauseVerification.factory_id == capa.factory_id)
        .order_by(CapaRootCauseVerification.created_at.desc()))
    rows = list(result.scalars().all())
    if actor_id is not None:
        await authorize_root(db, actor_id, capa.report_id)
    await _require_original_verification_sources(db, capa.report_id, actor_id)
    return rows


async def update_verification(db: AsyncSession, capa, vid, req: VerificationUpdate, user):
    # Parent-before-child lock ordering prevents a reviewed CAPA from being
    # changed by a stale verification row.
    actor_id = user.user_id
    capa = await lock_current_material_write(
        db, capa, actor_id, PermissionLevel.EDIT
    )
    await _require_original_verification_sources(db, capa.report_id, actor_id, vid)
    updates = req.model_dump(exclude_unset=True)
    if 'source_ref' in updates:
        await _require_verification_source_ref(db, actor_id, updates['source_ref'])
        new_ref = await _normalize_and_validate_source_ref(db, capa, updates['source_ref'])
    await _require_original_verification_sources(db, capa.report_id, actor_id, vid, lock=True)
    capa = await current_capa_actor_target(db, actor_id, capa.report_id, PermissionLevel.EDIT)
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
    old_source_ref = rec.source_ref
    await _require_original_verification_sources(db, capa.report_id, actor_id, vid)
    if "method" in updates:
        rec.method = updates["method"]
    if "result" in updates:
        rec.result = updates["result"]
    if "evidence_attachments" in updates:
        # 列为 NOT NULL（默认 []）：显式 null 视为清空到 []，避免 IntegrityError/500
        rec.evidence_attachments = updates["evidence_attachments"] or []
    source_ref_changed = False
    if "source_ref" in updates:
        if new_ref != old_source_ref:
            rec.source_ref = new_ref
            source_ref_changed = True
    if "conclusion" in updates and updates["conclusion"] is not None:
        rec.conclusion = updates["conclusion"]
    # is_verified 派生
    rec.is_verified = (rec.conclusion == "passed")
    if rec.is_verified:
        rec.verified_by = actor_id
        rec.verified_at = func.now()
    else:
        rec.verified_by = None
        rec.verified_at = None
    if rec.is_verified:
        _assert_verified_has_details(rec.method, rec.result, rec.evidence_attachments)
    # conclusion→failed 跃迁递增 retry_count（仅跃迁，防重复计；锁 capa 行防跨记录丢计数）
    conclusion_transitioned = False
    if old_conclusion != "failed" and rec.conclusion == "failed":
        capa.d4_retry_count = (capa.d4_retry_count or 0) + 1
        passed_fields = {
            "verification_id": str(vid),
            "method": rec.method,
            "root_cause_text": {"changed": True},
            "retry_count": capa.d4_retry_count,
            "source_ref": rec.source_ref,
        }
        # Spec §5.2: conclusion transition event carries final source_ref and
        # old_source_ref when Cause also changed in the same PATCH.
        if source_ref_changed:
            passed_fields["old_source_ref"] = old_source_ref
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_FAILED",
            changed_fields=passed_fields,
            operated_by=actor_id, factory_id=capa.factory_id,
        ))
        conclusion_transitioned = True
    elif old_conclusion != "passed" and rec.conclusion == "passed":
        passed_fields = {
            "verification_id": str(vid),
            "method": rec.method,
            "root_cause_text": {"changed": True},
            "source_ref": rec.source_ref,
        }
        if source_ref_changed:
            passed_fields["old_source_ref"] = old_source_ref
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D4_VERIFICATION_PASSED",
            changed_fields=passed_fields,
            operated_by=actor_id, factory_id=capa.factory_id,
        ))
        conclusion_transitioned = True
    if source_ref_changed:
        # UPDATED only when there is no conclusion transition (design §5.2):
        # simultaneous conclusion+Cause is carried on PASSED/FAILED alone.
        if not conclusion_transitioned:
            db.add(AuditLog(
                table_name="capa_eightd", record_id=capa.report_id,
                action="D4_VERIFICATION_UPDATED",
                changed_fields={"verification_id": str(vid), "source_ref": rec.source_ref,
                                "old_source_ref": old_source_ref},
                operated_by=actor_id, factory_id=capa.factory_id,
            ))
        # LINKAGE only on establish/change (not clear). cleared → rec.source_ref is None.
        if rec.source_ref is not None:
            db.add(_linkage_audit(capa, capa.fmea_ref_id, rec.source_ref["cause_node_id"],
                                  _LINKAGE_SOURCE_D4, actor_id))
    from app.services.capa_d4_provenance import invalidate_verification_proofs
    await invalidate_verification_proofs(db, vid)
    from app.services.capa_d4_material import bump_material, authorize_root
    await authorize_root(db, actor_id, capa.report_id, PermissionLevel.EDIT)
    await _require_original_verification_sources(db, capa.report_id, actor_id, vid)
    await bump_material(db, capa.report_id)
    await db.commit()
    await authorize_root(db, actor_id, capa.report_id)
    await _require_original_verification_sources(db, capa.report_id, actor_id, vid)
    await db.refresh(rec)
    await authorize_root(db, actor_id, capa.report_id)
    await _require_original_verification_sources(db, capa.report_id, actor_id, vid)
    return rec
