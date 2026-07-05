import uuid
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CapaD7NodeAction
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import D7NodeActionCreate


class ConflictError(Exception):
    """D7 动作幂等冲突（如已 auto_filled 再 auto-fill）—— handler 映 409。"""


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
    return fmea


async def record_d7_action(db: AsyncSession, capa, req: D7NodeActionCreate, user) -> CapaD7NodeAction:
    await _fetch_fmea_for_d7(db, capa, req.fmea_id)
    existing = await db.scalar(select(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id,
        CapaD7NodeAction.fmea_id == req.fmea_id,
        CapaD7NodeAction.failure_mode_node_id == req.failure_mode_node_id,
        CapaD7NodeAction.failure_cause_node_id == req.failure_cause_node_id,
    ))
    if existing is not None:
        if existing.action == "auto_filled":
            raise ValueError("已自动回填，不可改判")
        if existing.action == req.action and (existing.reason or None) == (req.reason or None):
            return existing   # 幂等：同 action + reason 不变
        old_action = existing.action
        old_reason = existing.reason
        existing.action = req.action
        existing.reason = req.reason
        existing.acted_by = user.user_id
        existing.acted_at = func.now()
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
        await db.commit()
        await db.refresh(existing)
        return existing
    rec = CapaD7NodeAction(
        capa_id=capa.report_id, factory_id=capa.factory_id,
        action=req.action, fmea_id=req.fmea_id,
        failure_mode_node_id=req.failure_mode_node_id,
        failure_cause_node_id=req.failure_cause_node_id,
        match_source=req.match_source, reason=req.reason, acted_by=user.user_id,
    )
    db.add(rec)
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
    await db.commit()
    await db.refresh(rec)
    return rec


async def list_d7_actions(db: AsyncSession, capa) -> list[CapaD7NodeAction]:
    result = await db.execute(
        select(CapaD7NodeAction)
        .where(CapaD7NodeAction.capa_id == capa.report_id,
               CapaD7NodeAction.factory_id == capa.factory_id)
        .order_by(CapaD7NodeAction.acted_at.desc()))
    return list(result.scalars().all())
