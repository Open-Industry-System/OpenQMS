import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.services.embedding_outbox import enqueue_embedding
from app.services.product_line_service import validate_product_line
from app.services.capa_d3_containment_service import _d3_to_d4_gate
from app.state_machines.eightd_state import EightDState, _linear_next, can_transition, capa_open_clause

EMBEDDING_FIELDS = {"d2_description", "d4_root_cause", "d5_correction", "d7_prevention"}


async def list_capas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    product_line: str | None = None,
    overdue: bool = False,
    pending_action: bool = False,
    allowed_product_line_codes: list[str] | None = None,
    factory_id: uuid.UUID | None = None,
) -> tuple[list[CAPAEightD], int]:
    from datetime import datetime
    now = datetime.now(UTC)

    query = select(CAPAEightD)
    count_query = select(func.count(CAPAEightD.report_id))

    if status:
        query = query.where(CAPAEightD.status == status)
        count_query = count_query.where(CAPAEightD.status == status)

    if product_line:
        query = query.where(CAPAEightD.product_line_code == product_line)
        count_query = count_query.where(CAPAEightD.product_line_code == product_line)

    if allowed_product_line_codes is not None:
        query = query.where(CAPAEightD.product_line_code.in_(allowed_product_line_codes))
        count_query = count_query.where(CAPAEightD.product_line_code.in_(allowed_product_line_codes))

    if factory_id is not None:
        query = query.where(CAPAEightD.factory_id == factory_id)
        count_query = count_query.where(CAPAEightD.factory_id == factory_id)

    if overdue:
        query = query.where(
            capa_open_clause(CAPAEightD.status),
            CAPAEightD.due_date < now.date(),
        )
        count_query = count_query.where(
            capa_open_clause(CAPAEightD.status),
            CAPAEightD.due_date < now.date(),
        )

    if pending_action:
        query = query.where(
            capa_open_clause(CAPAEightD.status)
        )
        count_query = count_query.where(
            capa_open_clause(CAPAEightD.status)
        )

    query = query.order_by(CAPAEightD.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_capa(db: AsyncSession, report_id: uuid.UUID) -> CAPAEightD | None:
    result = await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == report_id))
    return result.scalar_one_or_none()


async def create_capa(
    db: AsyncSession,
    title: str,
    document_no: str,
    severity: str,
    due_date,
    user_id: uuid.UUID,
    product_line_code: str = "DC-DC-100",
    factory_id: uuid.UUID | None = None,
) -> CAPAEightD:
    await validate_product_line(db, product_line_code)
    # Check if duplicate document_no exists
    existing_result = await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == document_no)
    )
    if existing_result.scalar_one_or_none():
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    report_id = uuid.uuid4()
    capa = CAPAEightD(
        report_id=report_id,
        title=title,
        document_no=document_no,
        severity=severity,
        due_date=due_date,
        product_line_code=product_line_code,
        created_by=user_id,
        factory_id=factory_id,
    )
    db.add(capa)

    # Audit log
    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=report_id,
        action="CREATE",
        changed_fields={
            "title": title,
            "document_no": document_no,
            "severity": severity,
            "due_date": str(due_date) if due_date else None,
            "product_line_code": product_line_code,
            "status": capa.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code, capa.factory_id)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    await db.refresh(capa)
    return capa


async def _create_capa_without_commit(
    db: AsyncSession,
    title: str,
    document_no: str,
    severity: str,
    due_date,
    user_id: uuid.UUID,
    product_line_code: str = "DC-DC-100",
    factory_id: uuid.UUID | None = None,
) -> CAPAEightD:
    """Create CAPA without committing — caller must commit."""
    await validate_product_line(db, product_line_code)
    # Check if duplicate document_no exists
    existing_result = await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == document_no)
    )
    if existing_result.scalar_one_or_none():
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    report_id = uuid.uuid4()
    capa = CAPAEightD(
        report_id=report_id,
        title=title,
        document_no=document_no,
        severity=severity,
        due_date=due_date,
        product_line_code=product_line_code,
        created_by=user_id,
        factory_id=factory_id,
    )
    db.add(capa)

    # Audit log
    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=report_id,
        action="CREATE",
        changed_fields={
            "title": title,
            "document_no": document_no,
            "severity": severity,
            "due_date": str(due_date) if due_date else None,
            "product_line_code": product_line_code,
            "status": capa.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.flush()
    except IntegrityError:
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    await db.refresh(capa)
    return capa


async def update_capa(
    db: AsyncSession,
    capa: CAPAEightD,
    update_data: dict,
    user_id: uuid.UUID,
) -> CAPAEightD:
    if "product_line_code" in update_data and update_data["product_line_code"] is not None:
        await validate_product_line(db, update_data["product_line_code"])

    # US-E2E-01.3：冻结字段后端约束（防 direct API 修改）
    _FROZEN_FIELDS_BY_STATUS = {
        EightDState.D7_COMPLETED.value: {"d7_prevention"},
        EightDState.D8_GATE_PENDING.value: {"d7_prevention", "d8_closure"},
        EightDState.D8_APPROVAL_PENDING.value: {"d7_prevention", "d8_closure"},
        EightDState.D8_CLOSURE.value: {"d7_prevention"},      # d8_closure 例外不冻结
        EightDState.ARCHIVED.value: {"d7_prevention", "d8_closure"},
    }
    frozen = _FROZEN_FIELDS_BY_STATUS.get(capa.status, set())
    violations = {k for k in update_data if k in frozen and update_data[k] is not None}
    if violations:
        raise ValueError(f"当前状态 {capa.status} 冻结字段不可修改: {sorted(violations)}")

    # Detect embedding field changes BEFORE mutating capa
    embedding_changed = {
        k for k, v in update_data.items()
        if k in EMBEDDING_FIELDS and getattr(capa, k) != v
    }

    # Task 14: d8_closure 变更且 status=D8_CLOSURE 时，先 savepoint 内 delete-and-rebuild
    # d8 lessons + 清理旧 embedding/outbox，成功后才 mutate capa.d8_closure（R4 fail-closed）。
    if (
        "d8_closure" in update_data
        and update_data["d8_closure"] is not None
        and capa.d8_closure != update_data["d8_closure"]
        and capa.status == "D8_CLOSURE"
    ):
        from app.services.capa_lessons_service import _extract_d8_with_cleanup
        await _extract_d8_with_cleanup(db, capa, update_data["d8_closure"])

    changed_fields = {}
    for key, value in update_data.items():
        if value is not None and hasattr(capa, key):
            old_value = getattr(capa, key)
            if old_value != value:
                if isinstance(value, (uuid.UUID, date, datetime)):
                    changed_fields[key] = str(value)
                else:
                    changed_fields[key] = value
                setattr(capa, key, value)

    if changed_fields:
        audit_log = AuditLog(
            table_name="capa_eightd",
            record_id=capa.report_id,
            action="UPDATE",
            changed_fields=changed_fields,
            operated_by=user_id,
        )
        db.add(audit_log)

    # Close linked risk alerts if CAPA reached D8_CLOSURE
    if capa.status == "D8_CLOSURE":
        from sqlalchemy import update

        from app.models.supplier_risk import SupplierRiskAlert
        await db.execute(
            update(SupplierRiskAlert)
            .where(SupplierRiskAlert.linked_capa_id == capa.report_id)
            .where(SupplierRiskAlert.status != "closed")
            .values(status="closed", handled_at=func.now())
        )

    if embedding_changed:
        await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code, capa.factory_id)
    await db.commit()
    await db.refresh(capa)
    return capa


async def _load_d7_gate_fmea_docs(db: AsyncSession, capa) -> list[dict]:
    # Canonical scope: capa 自己的 factory_id + product_line_code（R2+R5：不用用户 allowed_pls，
    # 不用整工厂）。FOR UPDATE 锁 FMEA 依赖集（R11：防并发 FMEA 编辑 race）。
    from app.models.fmea import FMEADocument

    result = await db.execute(
        select(FMEADocument).where(
            FMEADocument.factory_id == capa.factory_id,
            FMEADocument.product_line_code == capa.product_line_code,
        ).with_for_update()
    )
    return [
        {"fmea_id": f.fmea_id, "document_no": f.document_no, "graph_data": f.graph_data}
        for f in result.scalars().all()
    ]


async def _d7_completion_gate(db: AsyncSession, capa) -> None:
    from app.models.capa import CapaD7NodeAction
    from app.models.fmea import FMEADocument
    from app.services.capa_d7_action_service import recommendation_fingerprint

    # 1. 锁 capa 行（re-fetch FOR UPDATE，串行化并发 advance，决策 17）
    await db.execute(
        select(CAPAEightD).where(CAPAEightD.report_id == capa.report_id).with_for_update()
    )

    # 2. completeness check（R7+R8+R9：生成前跑，partial preload / 关联 FMEA 缺失 → fail-closed）
    fmea_count = await db.scalar(
        select(func.count()).select_from(FMEADocument).where(
            FMEADocument.factory_id == capa.factory_id,
            FMEADocument.product_line_code == capa.product_line_code,
        )
    )
    fmea_docs = await _load_d7_gate_fmea_docs(db, capa)
    if len(fmea_docs) != fmea_count:
        raise ValueError("D7 推荐重算异常：FMEA 预加载不完整")
    if capa.fmea_ref_id is not None and not any(
        d["fmea_id"] == capa.fmea_ref_id for d in fmea_docs
    ):
        raise ValueError("D7 推荐重算异常：FMEA 预加载不完整")

    # 3. 重算 D7 推荐（canonical scope，allowed_pls=[capa.product_line_code]）
    capa_data = {
        "fmea_ref_id": capa.fmea_ref_id,
        "fmea_node_id": capa.fmea_node_id,
        "d4_root_cause": capa.d4_root_cause or "",
        "d5_correction": capa.d5_correction,
        "product_line_code": capa.product_line_code,
    }
    recs = get_d7_recommendations(
        capa_data, fmea_docs, allowed_product_lines=[capa.product_line_code]
    )

    # 4. 真无推荐（completeness 通过 + count=0 + 无 linked）→ 平凡通过
    if not recs:
        return

    # 5. per-rec action check：capa_id 过滤（R8）+ recommendation_hash 匹配（R10+R11，同一 helper）
    #    + action IN (confirmed/skipped/auto_filled)（R6）。未处置/stale → fail-closed。
    unprocessed = 0
    for rec in recs:
        current_hash = recommendation_fingerprint(
            fmea_id=rec["fmea_id"],
            failure_mode_node_id=rec["failure_mode_node_id"],
            failure_cause_node_id=rec["failure_cause_node_id"],
            failure_mode_name=rec["failure_mode_name"],
            failure_cause_name=rec["failure_cause_name"],
            match_reason=rec["match_reason"],
            prevention_control_node_id=rec.get("prevention_control_node_id"),
            prevention_control_name=rec.get("prevention_control_name"),
        )
        cause_norm = rec["failure_cause_node_id"] or ""
        matched = await db.scalar(
            select(func.count()).select_from(CapaD7NodeAction).where(
                CapaD7NodeAction.capa_id == capa.report_id,
                CapaD7NodeAction.fmea_id == rec["fmea_id"],
                CapaD7NodeAction.failure_mode_node_id == rec["failure_mode_node_id"],
                func.coalesce(CapaD7NodeAction.failure_cause_node_id, "") == cause_norm,
                CapaD7NodeAction.recommendation_hash == current_hash,
                CapaD7NodeAction.action.in_(["confirmed", "skipped", "auto_filled"]),
            )
        )
        if not matched:
            unprocessed += 1
    if unprocessed:
        raise ValueError(
            f"D7 有 {unprocessed} 条推荐未处置或已 stale（FMEA 变更），不可关闭"
        )


async def _d8_doc_gate_gate(db: AsyncSession, capa: CAPAEightD) -> None:
    """D8_GATE_PENDING→D8_APPROVAL_PENDING: require latest decision=passed + C8/C9 freshness.

    Structured waiver: version_snapshot still lists every audited doc (including
    waived ones), bound to the version accepted at waiver time. C8 re-checks
    version_id + sha256 for every snap. For waived keypoints, also reconfirm
    target_key is still absent from that bound latest CP.
    """
    from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
    from app.services.capa_doc_gate_service import _build_allowlist, _compute_input_hash
    from app.services.version_service import get_latest_cp_version, get_latest_fmea_version

    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.is_current == True  # noqa: E712
        )
    )
    if analysis is None:
        raise ValueError("请先生成文档影响分析")
    candidates = await _build_allowlist(db, capa)
    if _compute_input_hash(capa, candidates) != analysis.analysis_input_hash:
        raise ValueError("分析输入已变更，请重新生成影响分析")
    decision = await db.scalar(
        select(CapaDocgDecision).where(CapaDocgDecision.analysis_id == analysis.analysis_id)
        .order_by(CapaDocgDecision.revision.desc(), CapaDocgDecision.decided_at.desc()).limit(1)
    )
    if decision is None:
        raise ValueError("请先运行文档审核")
    if decision.decision != "passed":
        raise ValueError(f"文档门禁未通过：{decision.decision}")
    if decision.waiver_reason is not None or decision.waiver_items is not None:
        from app.services.capa_doc_gate_waiver import validate_persisted_waiver
        await validate_persisted_waiver(db, analysis, decision)
    # C8 version freshness — re-check each snapshot against current latest.
    for snap in (decision.version_snapshot or []):
        doc_type = snap.get("doc_type")
        doc_id = uuid.UUID(str(snap["doc_id"]))
        if doc_type == "control_plan":
            latest = await get_latest_cp_version(db, doc_id)
        else:
            latest = await get_latest_fmea_version(db, doc_id)
        if (
            latest is None
            or str(latest.version_id) != snap.get("version_after_id")
            or latest.sha256_hash != snap.get("sha256")
        ):
            raise ValueError("文档已变更，请重新审核")


async def advance_capa(
    db: AsyncSession,
    capa: CAPAEightD,
    user_id: uuid.UUID,
    req: "AdvanceRequest | None" = None,  # 默认 None 保 9 个现存 3-arg 调用方（test_capa_d4_gate / recommendation lessons tests）
) -> CAPAEightD:
    from sqlalchemy import select
    from app.schemas.capa import AdvanceRequest

    if req is None:
        req = AdvanceRequest()  # 3-arg 调用方走线性 next（D1→D6→D7_PREVENTION、D8→ARCHIVED）

    # P1 并发安全：锁 capa 行 FOR UPDATE 串行化并发 advance。审批/驳回/归档边无闸口，
    # 若不锁，两并发请求都从同一状态推进 → 重复 TRANSITION/D8_APPROVED 审计/MES 事件。
    # populate_existing 强制把 identity-mapped 对象属性刷新为最新 DB 值，防 dep 加载的
    # capa.status 陈旧（另一事务已推进）→ can_transition 误判放行重复推进。
    await db.execute(
        select(CAPAEightD).where(CAPAEightD.report_id == capa.report_id)
        .with_for_update().execution_options(populate_existing=True)
    )

    current = EightDState(capa.status)
    target = req.target_state
    if target is None:
        target = _linear_next(current)  # 壳/分支状态 raise；D1→D6→D7_PREVENTION、D8→ARCHIVED 线性

    if not can_transition(current, target):
        raise ValueError(f"Cannot transition from {capa.status} to {target.value}")

    # per-edge 闸口分发
    if current == EightDState.D7_PREVENTION and target == EightDState.D7_COMPLETED:
        await _d7_completion_gate(db, capa)
        # savepoint 内抽 d7 lessons（fail-closed）
        from app.services.capa_lessons_service import _extract_lessons
        try:
            async with db.begin_nested():
                await _extract_lessons(db, capa, "d7")
                db.add(AuditLog(
                    table_name="capa_eightd",
                    record_id=capa.report_id,
                    action="LESSON_EXTRACTED",
                    changed_fields={"source_d_step": "d7"},
                    operated_by=user_id,
                    factory_id=capa.factory_id,
                    correlation_id=uuid.uuid5(
                        uuid.NAMESPACE_URL, f"lesson_extract_d7:{capa.report_id}"
                    ),
                ))
        except Exception as e:
            raise ValueError("D7 lessons 抽取失败，不可推进，请重试") from e
    elif current == EightDState.D8_GATE_PENDING and target == EightDState.D8_APPROVAL_PENDING:
        await _d8_doc_gate_gate(db, capa)
    elif current == EightDState.D8_APPROVAL_PENDING and target == EightDState.D8_CLOSURE:
        pass  # 权限由 require_advance_permission 强制；闸口即「审批」
    elif current == EightDState.D8_APPROVAL_PENDING and target == EightDState.D7_PREVENTION:
        if not req.reject_reason or not req.reject_reason.strip():
            raise ValueError("驳回需填写理由")
    elif current == EightDState.D3_INTERIM and target == EightDState.D4_ROOT_CAUSE:
        await _d3_to_d4_gate(db, capa)
    elif current == EightDState.D4_ROOT_CAUSE and target == EightDState.D5_CORRECTION:
        # 闸口绑定"当前"d4_root_cause：必须有已验证记录的 root_cause_text 与当前 d4_root_cause（空白归一化后）一致，
        # 防 d4_root_cause 被改后用陈旧验证记录放行
        current_rc = (capa.d4_root_cause or "").strip()
        if not current_rc:
            raise ValueError("D4→D5 需先填写根因并验证")
        cnt = await db.scalar(select(func.count()).select_from(CapaRootCauseVerification).where(
            CapaRootCauseVerification.capa_id == capa.report_id,
            CapaRootCauseVerification.factory_id == capa.factory_id,
            CapaRootCauseVerification.conclusion == "passed",
            CapaRootCauseVerification.root_cause_text == current_rc,
        ))
        if cnt < 1:
            raise ValueError("D4→D5 需当前根因已验证")
    # D1→D2、D2→D3、D3→D4、D5→D6、D6→D7_PREVENTION、D8→ARCHIVED：无闸口

    old_status = capa.status
    capa.status = target.value

    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=capa.report_id,
        action="TRANSITION",
        changed_fields={"old_status": old_status, "new_status": target.value},
        operated_by=user_id,
    )
    db.add(audit_log)

    # D7 skip reasons audit（仅 D7_PREVENTION→D7_COMPLETED）
    if req.d7_skip_reasons and old_status == "D7_PREVENTION":
        skip_log = AuditLog(
            table_name="capa_eightd",
            record_id=capa.report_id,
            action="D7_SKIP_CONFIRMATION",
            changed_fields={"skipped_nodes": req.d7_skip_reasons},
            operated_by=user_id,
        )
        db.add(skip_log)

    # 审批/驳回专项审计
    if current == EightDState.D8_APPROVAL_PENDING and target == EightDState.D8_CLOSURE:
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D8_APPROVED", changed_fields={"old_status": old_status, "new_status": target.value},
            operated_by=user_id,
        ))
    elif current == EightDState.D8_APPROVAL_PENDING and target == EightDState.D7_PREVENTION:
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D8_REJECTED",
            changed_fields={"reject_reason": req.reject_reason, "old_status": old_status, "new_status": target.value},
            operated_by=user_id,
        ))

    # Write to MES outbox before commit
    if capa.product_line_code and old_status != capa.status:
        from app.models.mes import MESConnection
        from app.services.mes_service import MESPushService

        query = select(MESConnection).where(
            MESConnection.is_active == True,
            MESConnection.product_line_code == capa.product_line_code,
        )
        result = await db.execute(query)
        for conn in result.scalars().all():
            cfg = conn.config or {}
            if conn.connector_type != "mock" and not cfg.get("push_enabled", False):
                continue
            await MESPushService.push_event(
                db,
                event_type="capa_status_change",
                connection_id=conn.connection_id,
                factory_id=conn.factory_id,
                payload={
                    "capa_id": str(capa.report_id),
                    "old_status": old_status,
                    "new_status": capa.status,
                    "changed_at": datetime.now(UTC).isoformat(),
                    "product_line_code": capa.product_line_code,
                },
            )

    await db.commit()  # existing commit includes outbox
    await db.refresh(capa)
    return capa


async def link_fmea(
    db: AsyncSession,
    capa: CAPAEightD,
    fmea_ref_id: uuid.UUID,
    user_id: uuid.UUID,
    fmea_node_id: str | None = None,
) -> CAPAEightD:
    from app.models.fmea import FMEADocument

    # Lock the CAPA row so concurrent identical links don't both read old and both write LINKAGE.
    await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == capa.report_id).with_for_update())
    await db.refresh(capa)
    old_fmea_ref_id = capa.fmea_ref_id
    old_fmea_node_id = capa.fmea_node_id
    fmea = await db.get(FMEADocument, fmea_ref_id)
    if fmea is None:
        raise LookupError("目标 FMEA 不存在")
    if fmea.factory_id != capa.factory_id:
        raise PermissionError("目标 FMEA 跨工厂")
    if fmea.product_line_code != capa.product_line_code:
        raise PermissionError("目标 FMEA 跨产品线")
    capa.fmea_ref_id = fmea_ref_id
    capa.fmea_node_id = fmea_node_id

    db.add(AuditLog(
        table_name="capa_eightd",
        record_id=capa.report_id,
        action="LINK_FMEA",
        changed_fields={
            "old_fmea_ref_id": str(old_fmea_ref_id) if old_fmea_ref_id else None,
            "new_fmea_ref_id": str(fmea_ref_id),
            "old_fmea_node_id": old_fmea_node_id,
            "new_fmea_node_id": fmea_node_id,
        },
        operated_by=user_id,
        factory_id=capa.factory_id,
    ))
    ref_changed = old_fmea_ref_id != fmea_ref_id
    node_changed = (old_fmea_node_id or None) != (fmea_node_id or None)
    if ref_changed or node_changed:
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="FMEA_LINKAGE_CREATED",
            changed_fields={
                "capa_id": str(capa.report_id),
                "fmea_id": str(fmea_ref_id),
                "node_id": fmea_node_id,
                "direction": "8d_to_fmea",
                "source": "header",
            },
            operated_by=user_id, factory_id=capa.factory_id,
        ))
    await db.commit()
    await db.refresh(capa)
    return capa


def get_d7_recommendations(
    capa_data: dict,
    fmea_docs: list[dict],
    allowed_product_lines: list[str] | None = None,
) -> list[dict]:
    """Compute D7 FMEA recommendations for a CAPA.

    Args:
        capa_data: dict with fmea_ref_id, fmea_node_id, d4_root_cause, d5_correction, product_line_code
        fmea_docs: list of dicts with fmea_id, document_no, graph_data (already filtered by product line)
        allowed_product_lines: user's accessible product line codes

    Returns:
        List of recommendation dicts matching D7Recommendation schema.
    """
    from app.utils.text import extract_keywords

    recommendations: list[dict] = []

    # Split into linked FMEA and other FMEAs
    linked_fmea_id = capa_data.get("fmea_ref_id")
    linked_fmea = None
    other_fmeas = []

    for doc in fmea_docs:
        if doc["fmea_id"] == linked_fmea_id:
            linked_fmea = doc
        else:
            other_fmeas.append(doc)

    # --- Linked matching ---
    if linked_fmea and linked_fmea.get("graph_data"):
        graph = linked_fmea["graph_data"]
        node_map = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])

        # Build reverse index: target -> list of (source, edge_type)
        reverse_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            reverse_edges.setdefault(e["target"], []).append((e["source"], e["type"]))

        # Build forward index: source -> list of (target, edge_type)
        forward_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))

        target_node_id = capa_data.get("fmea_node_id")
        target_node = node_map.get(target_node_id) if target_node_id else None

        failure_mode_ids: list[str] = []

        if target_node:
            if target_node["type"] == "FailureCause":
                # Find parent FailureMode via CAUSE_OF forward (FailureCause -> FailureMode)
                for tgt, etype in forward_edges.get(target_node_id, []):
                    if etype == "CAUSE_OF" and node_map.get(tgt, {}).get("type") == "FailureMode":
                        failure_mode_ids.append(tgt)
            elif target_node["type"] == "FailureMode":
                failure_mode_ids.append(target_node_id)
            else:
                # Function or other type: find FailureModes via HAS_FAILURE_MODE
                for tgt, etype in forward_edges.get(target_node_id, []):
                    if etype == "HAS_FAILURE_MODE" and node_map.get(tgt, {}).get("type") == "FailureMode":
                        failure_mode_ids.append(tgt)
        else:
            # No specific node: find FailureModes matching D4 keywords
            keywords = extract_keywords(capa_data.get("d4_root_cause", ""))
            for n in graph.get("nodes", []):
                if n.get("type") == "FailureMode":
                    name = n.get("name", "")
                    if any(kw in name or name in kw for kw in keywords):
                        failure_mode_ids.append(n["id"])

        # For each FailureMode, find FailureCauses and PreventionControls
        for fm_id in failure_mode_ids:
            fm_node = node_map.get(fm_id)
            if not fm_node:
                continue

            # Find FailureCauses via CAUSE_OF reverse (FailureCause --CAUSE_OF--> FailureMode)
            cause_ids = []
            for src, etype in reverse_edges.get(fm_id, []):
                if etype == "CAUSE_OF" and node_map.get(src, {}).get("type") == "FailureCause":
                    cause_ids.append(src)

            if not cause_ids:
                # No FailureCause -- skip (linked matching filters these out)
                continue

            for cause_id in cause_ids:
                cause_node = node_map.get(cause_id)
                # Find PreventionControl via PREVENTED_BY forward
                control_id = None
                control_name = None
                for tgt, etype in forward_edges.get(cause_id, []):
                    if etype == "PREVENTED_BY" and node_map.get(tgt, {}).get("type") == "PreventionControl":
                        control_id = tgt
                        control_name = node_map[tgt].get("name")
                        break

                recommendations.append({
                    "fmea_id": linked_fmea["fmea_id"],
                    "fmea_document_no": linked_fmea["document_no"],
                    "failure_mode_node_id": fm_id,
                    "failure_mode_name": fm_node.get("name", ""),
                    "failure_cause_node_id": cause_id,
                    "failure_cause_name": cause_node.get("name", "") if cause_node else None,
                    "prevention_control_node_id": control_id,
                    "prevention_control_name": control_name,
                    "match_source": "linked",
                    "match_reason": "关联FMEA失效模式",
                    "related_d4_keywords": extract_keywords(capa_data.get("d4_root_cause", "")),
                    "suggested_prevention": capa_data.get("d5_correction"),
                })

    # --- Keyword matching (other FMEAs) ---
    keywords = extract_keywords(capa_data.get("d4_root_cause", ""))
    if keywords and other_fmeas:
        seen_keys: set[str] = set()
        # Exclude already-added linked recommendations
        for r in recommendations:
            seen_keys.add(f"{r['fmea_id']}_{r['failure_mode_node_id']}")

        keyword_results: list[tuple[int, dict]] = []  # (match_count, rec)

        for doc in other_fmeas:
            # product_line filtering already done at query level
            graph = doc.get("graph_data")
            if not graph:
                continue

            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            edges = graph.get("edges", [])

            reverse_edges_kw: dict[str, list[tuple[str, str]]] = {}
            for e in edges:
                reverse_edges_kw.setdefault(e["target"], []).append((e["source"], e["type"]))

            forward_edges_kw: dict[str, list[tuple[str, str]]] = {}
            for e in edges:
                forward_edges_kw.setdefault(e["source"], []).append((e["target"], e["type"]))

            # Pre-index FailureCause names+descriptions per FailureMode for broader keyword matching
            fm_cause_texts: dict[str, list[str]] = {}  # fm_id -> [cause_name, cause_desc, ...]
            for e in edges:
                if e["type"] == "CAUSE_OF":
                    cause_node = node_map.get(e["source"])
                    if cause_node and cause_node.get("type") == "FailureCause":
                        texts = [cause_node.get("name", "")]
                        if cause_node.get("description"):
                            texts.append(cause_node["description"])
                        fm_cause_texts.setdefault(e["target"], []).extend(texts)

            for n in graph.get("nodes", []):
                if n.get("type") != "FailureMode":
                    continue

                # Match against FailureMode name/description AND its FailureCause name/description
                all_text = [n.get("name", "")]
                if n.get("description"):
                    all_text.append(n["description"])
                all_text.extend(fm_cause_texts.get(n["id"], []))
                matched_kws = [kw for kw in keywords if any(kw in t or t in kw for t in all_text)]
                if not matched_kws:
                    continue

                # Find FailureCauses
                cause_ids = []
                for src, etype in reverse_edges_kw.get(n["id"], []):
                    if etype == "CAUSE_OF" and node_map.get(src, {}).get("type") == "FailureCause":
                        cause_ids.append(src)

                if not cause_ids:
                    # No FailureCause -- include with null cause/control, disable auto-fill
                    dedup_key = f"{doc['fmea_id']}_{n['id']}_none"
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)
                    keyword_results.append((len(matched_kws), {
                        "fmea_id": doc["fmea_id"],
                        "fmea_document_no": doc["document_no"],
                        "failure_mode_node_id": n["id"],
                        "failure_mode_name": n.get("name", ""),
                        "failure_cause_node_id": None,
                        "failure_cause_name": None,
                        "prevention_control_node_id": None,
                        "prevention_control_name": None,
                        "match_source": "keyword",
                        "match_reason": f"关键词匹配: {', '.join(matched_kws)}",
                        "related_d4_keywords": matched_kws,
                        "suggested_prevention": capa_data.get("d5_correction"),
                    }))
                    continue

                for cause_id in cause_ids:
                    dedup_key = f"{doc['fmea_id']}_{n['id']}_{cause_id}"
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    cause_node = node_map.get(cause_id)
                    control_id = None
                    control_name = None
                    for tgt, etype in forward_edges_kw.get(cause_id, []):
                        if etype == "PREVENTED_BY" and node_map.get(tgt, {}).get("type") == "PreventionControl":
                            control_id = tgt
                            control_name = node_map[tgt].get("name")
                            break

                    keyword_results.append((len(matched_kws), {
                        "fmea_id": doc["fmea_id"],
                        "fmea_document_no": doc["document_no"],
                        "failure_mode_node_id": n["id"],
                        "failure_mode_name": n.get("name", ""),
                        "failure_cause_node_id": cause_id,
                        "failure_cause_name": cause_node.get("name", "") if cause_node else None,
                        "prevention_control_node_id": control_id,
                        "prevention_control_name": control_name,
                        "match_source": "keyword",
                        "match_reason": f"关键词匹配: {', '.join(matched_kws)}",
                        "related_d4_keywords": matched_kws,
                        "suggested_prevention": capa_data.get("d5_correction"),
                    }))

        # Sort by match count descending, take top 5
        keyword_results.sort(key=lambda x: x[0], reverse=True)
        for _, rec in keyword_results[:5]:
            recommendations.append(rec)

    # --- 规则引擎兜底：FMEA 命中为空时，给出预防措施建议让 D7 节点动作可操作 ---
    if not recommendations:
        recommendations = _d7_rule_engine_fallback(capa_data)

    return recommendations


def _d7_rule_engine_fallback(capa_data: dict) -> list[dict]:
    """无 FMEA 命中时的 D7 规则引擎兜底：基于 D2/D4 文本生成预防措施建议。

    每条兜底推荐无关联 FMEA（fmea_id=None），用合成 failure_mode_node_id（rule:<hash>）
    作为动作 key，使 D7RecPanel 的 d7-confirm/d7-skip 可操作（d7-auto-fill 因无 cause 节点
    自动禁用）。AP 默认 M，S/O/D 不臆造。
    """
    import hashlib

    from app.services.recommendation_service import RuleEngine
    from app.utils.text import extract_keywords

    text = capa_data.get("d4_root_cause") or capa_data.get("d2_description", "")
    if not text.strip():
        return []
    engine = RuleEngine()
    result = engine.evaluate("measure", {"failure_mode": text, "ap": "M"})
    keywords = extract_keywords(text)
    recs: list[dict] = []
    for s in result.suggestions:
        cat = s.explanation or "预防措施"
        if cat == "检测措施":
            cat = "探测措施"
        synthetic_key = "rule:" + hashlib.sha256(s.name.encode()).hexdigest()[:16]
        recs.append({
            "fmea_id": None,
            "fmea_document_no": None,
            "failure_mode_node_id": synthetic_key,
            "failure_mode_name": None,
            "failure_cause_node_id": None,
            "failure_cause_name": None,
            "prevention_control_node_id": None,
            "prevention_control_name": None,
            "match_source": "rule",
            "match_reason": "规则引擎预防建议",
            "related_d4_keywords": keywords,
            "suggested_prevention": s.name,
        })
    return recs


LINK_SOURCES_ORDER = ["d4_cause", "d7_failure_cause", "d7_failure_mode", "d7_prevention", "header"]


async def get_capas_by_fmea_node(
    db: AsyncSession,
    fmea_id: str,
    fmea_node_id: str | None = None,
    *,
    accessible_factory_ids: list[uuid.UUID] | None = None,
    effective_factory_id: uuid.UUID | None = None,
) -> list[dict]:
    """Three-source reverse lookup: header + D7(adopted) + D4(source_ref).

    Factory filtering: effective_factory_id (==) if set, else IN accessible_factory_ids,
    else (None = group admin, no effective) no factory predicate.
    """
    from app.models.capa import CapaD7NodeAction, CapaRootCauseVerification

    def _factory_predicate(model):
        if effective_factory_id is not None:
            return model.factory_id == effective_factory_id
        if accessible_factory_ids is not None:
            if not accessible_factory_ids:
                return model.factory_id == uuid.UUID(int=0)  # impossible → empty
            return model.factory_id.in_(accessible_factory_ids)
        return None  # no predicate

    sources_by_capa: dict[uuid.UUID, set[str]] = {}

    def _add(capa_id, *sources):
        sources_by_capa.setdefault(capa_id, set()).update(sources)

    # 1. header
    hq = select(CAPAEightD).where(CAPAEightD.fmea_ref_id == fmea_id)
    if fmea_node_id:
        hq = hq.where(CAPAEightD.fmea_node_id == fmea_node_id)
    fp = _factory_predicate(CAPAEightD)
    if fp is not None:
        hq = hq.where(fp)
    for c in (await db.execute(hq)).scalars().all():
        _add(c.report_id, "header")

    # 2. D7 (confirmed / auto_filled only)
    # Reverse-lookup is multi-source union (design §5.1): with fmea_node_id,
    # OR-match FM/cause/prevention and contribute each hit tag; without node,
    # contribute all non-null d7_* sources. Write-path LINKAGE remains
    # primary-only via _linkage_node_for_rec (prevention → cause → mode).
    dq = select(CapaD7NodeAction).where(
        CapaD7NodeAction.fmea_id == fmea_id,
        CapaD7NodeAction.action.in_(["confirmed", "auto_filled"]),
    )
    fpd = _factory_predicate(CapaD7NodeAction)
    if fpd is not None:
        dq = dq.where(fpd)
    for a in (await db.execute(dq)).scalars().all():
        hits: list[str] = []
        if a.prevention_control_node_id and (
            fmea_node_id is None or a.prevention_control_node_id == fmea_node_id
        ):
            hits.append("d7_prevention")
        if a.failure_cause_node_id and (
            fmea_node_id is None or a.failure_cause_node_id == fmea_node_id
        ):
            hits.append("d7_failure_cause")
        if a.failure_mode_node_id and (
            fmea_node_id is None or a.failure_mode_node_id == fmea_node_id
        ):
            hits.append("d7_failure_mode")
        if hits:
            _add(a.capa_id, *hits)

    # 3. D4 source_ref
    vq = select(CapaRootCauseVerification, CAPAEightD).join(
        CAPAEightD, CAPAEightD.report_id == CapaRootCauseVerification.capa_id
    ).where(CapaRootCauseVerification.source_ref["fmea_id"].astext == fmea_id)
    fpv = _factory_predicate(CAPAEightD)
    if fpv is not None:
        vq = vq.where(fpv)
    if fmea_node_id:
        vq = vq.where(CapaRootCauseVerification.source_ref["cause_node_id"].astext == fmea_node_id)
    for v, c in (await db.execute(vq)).all():
        _add(c.report_id, "d4_cause")

    if not sources_by_capa:
        return []

    capa_ids = list(sources_by_capa.keys())
    capas = (await db.execute(select(CAPAEightD).where(CAPAEightD.report_id.in_(capa_ids)))).scalars().all()
    rows = []
    for c in capas:
        ordered = [s for s in LINK_SOURCES_ORDER if s in sources_by_capa[c.report_id]]
        rows.append({
            "report_id": str(c.report_id),
            "document_no": c.document_no,
            "title": c.title,
            "status": c.status,
            "product_line_code": c.product_line_code,
            "link_sources": ordered,
        })
    rows.sort(key=lambda r: r["document_no"])
    return rows
