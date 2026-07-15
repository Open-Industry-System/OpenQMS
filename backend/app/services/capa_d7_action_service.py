import copy
import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CapaD7NodeAction
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import D7AutoFillRequest, D7NodeActionCreate
from app.services.fmea_service import _apply_fmea_update
from app.state_machines.eightd_state import EightDState


def recommendation_fingerprint(
    *,
    fmea_id,
    failure_mode_node_id,
    failure_cause_node_id,
    failure_mode_name,
    failure_cause_name,
    match_reason,
    prevention_control_node_id,
    prevention_control_name,
) -> str:
    # Canonical content hash (R11): record + gate 调同一函数，byte-identical 输入 → 相同输出。
    # node_id 稳定 + name/reason/prevention 内容指纹：FMEA 节点改名/推荐内容变/prevention 变 → hash 变 → stale。
    raw = (
        f"{fmea_id}|{failure_mode_node_id}|{failure_cause_node_id or ''}|"
        f"{failure_mode_name}|{failure_cause_name or ''}|{match_reason}|"
        f"{prevention_control_node_id or ''}|{prevention_control_name or ''}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def _compute_current_d7_recs(db: AsyncSession, capa) -> list[dict]:
    # 复用 D7 recommend 端点的 fmea_docs 预加载方式（canonical scope: capa 自己的工厂+产品线），
    # 重算当前 D7 推荐集。record + gate 均调此函数，确保 key/hash 一致。
    from app.services.capa_service import get_d7_recommendations

    result = await db.execute(
        select(FMEADocument).where(
            FMEADocument.factory_id == capa.factory_id,
            FMEADocument.product_line_code == capa.product_line_code,
        )
    )
    fmea_docs = [
        {"fmea_id": f.fmea_id, "document_no": f.document_no, "graph_data": f.graph_data}
        for f in result.scalars().all()
    ]
    capa_data = {
        "fmea_ref_id": capa.fmea_ref_id,
        "fmea_node_id": capa.fmea_node_id,
        "d4_root_cause": capa.d4_root_cause or "",
        "d5_correction": capa.d5_correction,
        "product_line_code": capa.product_line_code,
    }
    return get_d7_recommendations(
        capa_data, fmea_docs, allowed_product_lines=[capa.product_line_code]
    )


def _find_rec(recs, *, fmea_id, failure_mode_node_id, failure_cause_node_id):
    target_cause = failure_cause_node_id or ""
    for r in recs:
        if (
            r["fmea_id"] == fmea_id
            and r["failure_mode_node_id"] == failure_mode_node_id
            and (r["failure_cause_node_id"] or "") == target_cause
        ):
            return r
    return None


def _hash_for_rec(rec) -> str:
    return recommendation_fingerprint(
        fmea_id=rec["fmea_id"],
        failure_mode_node_id=rec["failure_mode_node_id"],
        failure_cause_node_id=rec["failure_cause_node_id"],
        failure_mode_name=rec["failure_mode_name"],
        failure_cause_name=rec["failure_cause_name"],
        match_reason=rec["match_reason"],
        prevention_control_node_id=rec.get("prevention_control_node_id"),
        prevention_control_name=rec.get("prevention_control_name"),
    )


def _prevention_fields_from_rec(rec):
    """Copy canonical Prevention fields for an action row (confirmed/skipped)."""
    return {
        "prevention_control_node_id": rec.get("prevention_control_node_id"),
        "prevention_control_name_before": rec.get("prevention_control_name"),
        "prevention_control_name_after": rec.get("prevention_control_name"),  # confirmed/skipped: before==after
    }


def _linkage_node_for_rec(rec):
    """Fallback node_id/source for LINKAGE: prevention → cause → mode (first non-null)."""
    if rec.get("prevention_control_node_id"):
        return rec["prevention_control_node_id"], "d7_prevention"
    if rec.get("failure_cause_node_id"):
        return rec["failure_cause_node_id"], "d7_failure_cause"
    return rec["failure_mode_node_id"], "d7_failure_mode"


def _d7_linkage_audit(capa, rec, user_id) -> AuditLog:
    node_id, source = _linkage_node_for_rec(rec)
    return AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="FMEA_LINKAGE_CREATED",
        changed_fields={
            "capa_id": str(capa.report_id),
            "fmea_id": str(rec["fmea_id"]),
            "node_id": node_id,
            "direction": "8d_to_fmea",
            "source": source,
        },
        operated_by=user_id, factory_id=capa.factory_id,
    )


class ConflictError(Exception):
    """D7 动作幂等冲突（如已 auto_filled 再 auto-fill）—— handler 映 409。"""


async def _assert_d7_stage(capa) -> None:
    # D7 写操作（confirm/skip/auto-fill）只能在 D7_PREVENTION 阶段执行，防跨阶段写入
    if capa.status != EightDState.D7_PREVENTION:
        raise ValueError("D7 动作只能在 D7 预防复发阶段执行")


async def _fetch_fmea_for_d7(db: AsyncSession, capa, fmea_id, *, lock: bool = False) -> FMEADocument:
    # lock=True 时 SELECT ... FOR UPDATE，串行化并发 auto-fill（必须在读 graph_data 之前锁，
    # 否则另一事务可能在读 graph 与 _apply_fmea_update 之间改 FMEA graph）
    if lock:
        fmea = (await db.execute(
            select(FMEADocument).where(FMEADocument.fmea_id == fmea_id).with_for_update()
        )).scalar_one_or_none()
    else:
        fmea = await db.get(FMEADocument, fmea_id)
    if fmea is None:
        raise LookupError("目标 FMEA 不存在")
    if fmea.factory_id != capa.factory_id:
        raise PermissionError("目标 FMEA 跨工厂")
    # 产品线隔离：目标 FMEA 必须与 CAPA 同产品线，防同工厂跨产品线写入（绕过 pl_scope）
    if fmea.product_line_code != capa.product_line_code:
        raise PermissionError("目标 FMEA 跨产品线")
    return fmea


async def record_d7_action(db: AsyncSession, capa, req: D7NodeActionCreate, user) -> CapaD7NodeAction:
    await _assert_d7_stage(capa)
    # 规则引擎兜底推荐无关联 FMEA（fmea_id=None）——跳过 FMEA 校验，仅记录 confirm/skip
    if req.fmea_id is not None:
        await _fetch_fmea_for_d7(db, capa, req.fmea_id)
    # R13: 重算当前 D7 推荐集，要求 req 的 key 在其中——防 stale UI / 恶意 key 写入悬空 action。
    # key 命中 → 用 canonical helper 算 recommendation_hash；未命中 → 400，不落 action。
    current_recs = await _compute_current_d7_recs(db, capa)
    rec = _find_rec(
        current_recs,
        fmea_id=req.fmea_id,
        failure_mode_node_id=req.failure_mode_node_id,
        failure_cause_node_id=req.failure_cause_node_id,
    )
    if rec is None:
        raise ValueError("D7 推荐 key 不存在于当前推荐集")
    rec_hash = _hash_for_rec(rec)
    existing_query = select(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id,
        CapaD7NodeAction.failure_mode_node_id == req.failure_mode_node_id,
        CapaD7NodeAction.failure_cause_node_id == req.failure_cause_node_id,
    )
    if req.fmea_id is None:
        existing_query = existing_query.where(CapaD7NodeAction.fmea_id.is_(None))
    else:
        existing_query = existing_query.where(CapaD7NodeAction.fmea_id == req.fmea_id)
    existing = await db.scalar(existing_query)
    if existing is not None:
        if existing.action == "auto_filled":
            raise ValueError("已自动回填，不可改判")
        if existing.action == req.action and (existing.reason or None) == (req.reason or None):
            # 幂等：同 action + reason 不变，但仍刷新 recommendation_hash——
            # 若 FMEA 节点改名/推荐内容变，重新确认应让 hash 与当前 rec 保持一致，避免 stale 锁死。
            existing.recommendation_hash = rec_hash
            pv = _prevention_fields_from_rec(rec)
            existing.prevention_control_node_id = pv["prevention_control_node_id"]
            existing.prevention_control_name_before = pv["prevention_control_name_before"]
            existing.prevention_control_name_after = pv["prevention_control_name_after"]
            await db.commit()
            await db.refresh(existing)
            return existing
        old_action = existing.action
        old_reason = existing.reason
        existing.action = req.action
        existing.reason = req.reason
        existing.recommendation_hash = rec_hash
        existing.acted_by = user.user_id
        existing.acted_at = func.now()
        pv = _prevention_fields_from_rec(rec)
        existing.prevention_control_node_id = pv["prevention_control_node_id"]
        existing.prevention_control_name_before = pv["prevention_control_name_before"]
        existing.prevention_control_name_after = pv["prevention_control_name_after"]
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D7_ACTION_CHANGED",
            changed_fields={
                "fmea_id": str(req.fmea_id),
                "failure_mode_node_id": req.failure_mode_node_id,
                "failure_cause_node_id": req.failure_cause_node_id,
                "old_action": old_action, "new_action": req.action,
                "old_reason": old_reason, "new_reason": req.reason,
            },
            operated_by=user.user_id, factory_id=capa.factory_id,
        ))
        if old_action == "skipped" and req.action == "confirmed" and req.fmea_id is not None:
            db.add(_d7_linkage_audit(capa, rec, user.user_id))
        await db.commit()
        await db.refresh(existing)
        return existing
    pv = _prevention_fields_from_rec(rec)
    rec_row = CapaD7NodeAction(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        action=req.action, fmea_id=req.fmea_id,
        failure_mode_node_id=req.failure_mode_node_id,
        failure_cause_node_id=req.failure_cause_node_id,
        match_source=req.match_source, reason=req.reason, acted_by=user.user_id,
        recommendation_hash=rec_hash,
        prevention_control_node_id=pv["prevention_control_node_id"],
        prevention_control_name_before=pv["prevention_control_name_before"],
        prevention_control_name_after=pv["prevention_control_name_after"],
    )
    db.add(rec_row)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action=f"D7_NODE_{req.action.upper()}",
        changed_fields={
            "fmea_id": str(req.fmea_id),
            "failure_mode_node_id": req.failure_mode_node_id,
            "failure_cause_node_id": req.failure_cause_node_id,
            "match_source": req.match_source, "reason": req.reason,
        },
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    if req.fmea_id is not None and req.action == "confirmed":
        db.add(_d7_linkage_audit(capa, rec, user.user_id))
    capa_id = capa.report_id  # 捕获标量，供 rollback（expire capa）后的重试查询使用
    try:
        await db.commit()
    except IntegrityError:
        # 并发 confirm/skip 同节点：另一事务先插 → ix_capa_d7_node_unique 兜底。
        # 回滚后查既有行返回（幂等），不泄漏 500；既有行不存在则重新抛（非 dedupe 冲突）
        # rollback 会 expire capa；async 下访问 capa.report_id 会 MissingGreenlet → 用捕获的标量 capa_id
        await db.rollback()
        retry_query = select(CapaD7NodeAction).where(
            CapaD7NodeAction.capa_id == capa_id,
            CapaD7NodeAction.failure_mode_node_id == req.failure_mode_node_id,
            CapaD7NodeAction.failure_cause_node_id == req.failure_cause_node_id,
        )
        if req.fmea_id is None:
            retry_query = retry_query.where(CapaD7NodeAction.fmea_id.is_(None))
        else:
            retry_query = retry_query.where(CapaD7NodeAction.fmea_id == req.fmea_id)
        existing = await db.scalar(retry_query)
        if existing is None:
            raise
        return existing
    await db.refresh(rec_row)
    return rec_row


async def list_d7_actions(db: AsyncSession, capa) -> list[CapaD7NodeAction]:
    result = await db.execute(
        select(CapaD7NodeAction)
        .where(CapaD7NodeAction.capa_id == capa.report_id,
               CapaD7NodeAction.factory_id == capa.factory_id)
        .order_by(CapaD7NodeAction.acted_at.desc()))
    return list(result.scalars().all())


async def auto_fill_d7(db: AsyncSession, capa, req: D7AutoFillRequest, user):
    if not capa.d5_correction:
        raise ValueError("D5 永久措施为空，无法自动回填")
    if req.fmea_id is None or not req.failure_cause_node_id:
        # 规则引擎兜底推荐无 FMEA 节点，不支持 auto-fill（UI 已禁用，兜底拒绝）
        raise ValueError("规则引擎兜底推荐不支持自动回填到 FMEA")
    await _assert_d7_stage(capa)
    # 锁 FMEA 行（FOR UPDATE），串行化并发 auto-fill；必须在读 graph_data 之前锁，
    # 否则两个并发请求都读到旧 graph、都过既有行检查，一个 commit 时撞 unique index → 500
    fmea = await _fetch_fmea_for_d7(db, capa, req.fmea_id, lock=True)
    # 先查既有行：已 auto_filled 直接 409，必须在改 FMEA graph 之前，避免污染 session
    existing = await db.scalar(select(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id,
        CapaD7NodeAction.fmea_id == req.fmea_id,
        CapaD7NodeAction.failure_mode_node_id == req.failure_mode_node_id,
        CapaD7NodeAction.failure_cause_node_id == req.failure_cause_node_id,
    ))
    if existing is not None and existing.action == "auto_filled":
        raise ConflictError("已自动回填")
    # 校验目标节点存在于 graph 且 cause→mode CAUSE_OF 关系匹配，防过期/恶意请求写悬空边
    pre_graph = fmea.graph_data or {"nodes": [], "edges": []}
    node_ids = {n.get("id") for n in pre_graph.get("nodes", [])}
    if req.failure_mode_node_id not in node_ids:
        raise ValueError("目标失效模式节点不存在于 FMEA graph")
    if req.failure_cause_node_id not in node_ids:
        raise ValueError("目标失效原因节点不存在于 FMEA graph")
    if not any(
        e.get("source") == req.failure_cause_node_id
        and e.get("target") == req.failure_mode_node_id
        and e.get("type") == "CAUSE_OF"
        for e in pre_graph.get("edges", [])
    ):
        raise ValueError("失效原因与失效模式无 CAUSE_OF 关系")
    # R13: graph 结构校验通过后、mutation 前，重算当前 D7 推荐集并要求 req key 在其中。
    # 防 stale UI / 恶意 key 写悬空 action；命中 → 用 canonical helper 算 recommendation_hash。
    current_recs = await _compute_current_d7_recs(db, capa)
    rec_match = _find_rec(
        current_recs,
        fmea_id=req.fmea_id,
        failure_mode_node_id=req.failure_mode_node_id,
        failure_cause_node_id=req.failure_cause_node_id,
    )
    if rec_match is None:
        raise ValueError("D7 推荐 key 不存在于当前推荐集")
    graph = copy.deepcopy(fmea.graph_data or {"nodes": [], "edges": []})
    ctrl_node = None
    name_before = None
    for e in graph["edges"]:
        if e["source"] == req.failure_cause_node_id and e["type"] == "PREVENTED_BY":
            for n in graph["nodes"]:
                if n["id"] == e["target"] and n["type"] == "PreventionControl":
                    ctrl_node = n
                    name_before = n.get("name")
                    break
    is_new = ctrl_node is None
    if is_new:
        ctrl_id = str(uuid.uuid4())
        graph["nodes"].append({
            "id": ctrl_id, "type": "PreventionControl", "name": capa.d5_correction,
            "severity": 1, "occurrence": 1, "detection": 1,
        })
        graph["edges"].append({
            "source": req.failure_cause_node_id, "target": ctrl_id, "type": "PREVENTED_BY",
        })
        ctrl_node = graph["nodes"][-1]
    else:
        ctrl_node["name"] = capa.d5_correction
    # 复用 FMEA 全部副作用（lock_version++/outbox/cache/embedding），不 commit
    await _apply_fmea_update(db, fmea, title=None, graph_data=graph, user_id=user.user_id)
    # Post-mutation hash: prevention now exists/renamed in ctrl_node. Gate recomputes from
    # the mutated FMEA, so the stored hash must reflect the post-mutation prevention value
    # (otherwise the just-auto-filled action is immediately stale and D7 can't advance).
    post_rec = {
        **rec_match,
        "prevention_control_node_id": ctrl_node["id"],
        "prevention_control_name": ctrl_node["name"],
    }
    rec_hash = _hash_for_rec(post_rec)

    if existing is not None:
        # existing.action in {confirmed, skipped} → 升级为 auto_filled（auto_filled 已在上方提前 409）
        old_action = existing.action
        existing.action = "auto_filled"
        existing.prevention_control_node_id = ctrl_node["id"]
        existing.prevention_control_name_before = name_before
        existing.prevention_control_name_after = capa.d5_correction
        existing.recommendation_hash = rec_hash
        existing.acted_by = user.user_id
        existing.acted_at = func.now()
        rec = existing
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id,
            action="D7_ACTION_CHANGED",
            changed_fields={"old_action": old_action, "new_action": "auto_filled",
                            "prevention_control_node_id": ctrl_node["id"]},
            operated_by=user.user_id, factory_id=capa.factory_id,
        ))
    else:
        rec = CapaD7NodeAction(
            capa_id=capa.report_id, factory_id=capa.factory_id,
            action="auto_filled", fmea_id=req.fmea_id,
            failure_mode_node_id=req.failure_mode_node_id,
            failure_cause_node_id=req.failure_cause_node_id,
            match_source=req.match_source,
            prevention_control_node_id=ctrl_node["id"],
            prevention_control_name_before=name_before,
            prevention_control_name_after=capa.d5_correction,
            acted_by=user.user_id,
            recommendation_hash=rec_hash,
        )
        db.add(rec)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="D7_AUTO_FILLED_FMEA",
        changed_fields={
            "fmea_id": str(req.fmea_id), "failure_cause_node_id": req.failure_cause_node_id,
            "prevention_control_node_id": ctrl_node["id"],
            "name_before": name_before, "name_after": capa.d5_correction,
        },
        operated_by=user.user_id, factory_id=capa.factory_id,
    ))
    if req.fmea_id is not None:
        db.add(_d7_linkage_audit(capa, {
            "fmea_id": req.fmea_id,
            "prevention_control_node_id": ctrl_node["id"],
            "failure_cause_node_id": req.failure_cause_node_id,
            "failure_mode_node_id": req.failure_mode_node_id,
        }, user.user_id))
    try:
        await db.commit()
    except IntegrityError:
        # 并发 auto-fill：另一事务先 commit 同 (capa, fmea, fm, cause) → ix_capa_d7_node_unique 兜底
        # 命中 → 回滚后映 409（不是 500），与"已自动回填"语义一致
        await db.rollback()
        raise ConflictError("已自动回填")
    await db.refresh(rec)
    return rec, {
        "prevention_control_node_id": ctrl_node["id"],
        "prevention_control_name_after": capa.d5_correction,
        "is_new_control": is_new,
    }
