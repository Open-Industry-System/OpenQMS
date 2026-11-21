"""Read-only paginated queries for audit / login / system logs (tenant-scoped)."""
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.login_audit_log import LoginAuditLog
from app.models.system_log import SystemLog
from app.models.user import User


def _bounds(filters: dict[str, Any]):
    start = filters.get("start")
    end = filters.get("end")
    return start, end


async def list_audit_logs(db: AsyncSession, filters: dict[str, Any], page: int, page_size: int, *, actor_id=None):
    table_name = filters.get("table_name")
    action = filters.get("action")
    operated_by = filters.get("operated_by")  # username
    start, end = _bounds(filters)

    # Unbound historical draft errors can echo FMEA input. Project in SQL;
    # preserve the original record at rest without reading that freeform text.
    unverified = func.jsonb_build_object('error', '历史错误详情未核实',
        'error_code', 'DRAFT_ERROR_DETAILS_UNVERIFIED')
    object_fields = case((AuditLog.changed_fields['error'].astext.is_not(None),
        AuditLog.changed_fields.op('-')('error').op('||')(unverified)), else_=AuditLog.changed_fields)
    draft_fields = case((func.jsonb_typeof(AuditLog.changed_fields) == 'object', object_fields),
        else_=unverified)
    verification_history = AuditLog.action.in_(['D4_VERIFICATION_PASSED', 'D4_VERIFICATION_FAILED', 'D4_VERIFICATION_UPDATED'])
    # Historic freeform payloads have no immutable source binding. The current
    # verification.source_ref is editable, so it cannot attest an older audit.
    from app.models.capa import CapaRootCauseVerification
    verification_id = AuditLog.changed_fields['verification_id'].astext
    bound_verification = select(CapaRootCauseVerification.verification_id).where(
        CapaRootCauseVerification.capa_id == AuditLog.record_id,
        CapaRootCauseVerification.verification_id.cast(String) == verification_id).exists()
    safe_reference = case(((func.jsonb_typeof(AuditLog.changed_fields) == 'object')
        & (func.jsonb_typeof(AuditLog.changed_fields['verification_id']) == 'string')
        & verification_id.op('~')('^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
        & bound_verification, verification_id), else_=None)
    verification_fields = func.jsonb_build_object(
        'verification_id', safe_reference,
        'details_status', 'historical_audit_body_unattested')
    projected_fields = case((verification_history, verification_fields),
        (AuditLog.action == 'AI_DRAFT', draft_fields),
        else_=AuditLog.changed_fields).label('changed_fields')
    projected_old = case((verification_history, None), else_=AuditLog.old_values).label('old_values')
    projected_new = case((verification_history, None), else_=AuditLog.new_values).label('new_values')
    stmt = select(AuditLog.log_id, AuditLog.table_name, AuditLog.record_id, AuditLog.action,
        projected_fields, projected_old, projected_new, AuditLog.ip_address,
        AuditLog.operated_at, User.username.label('username')).outerjoin(
            User, AuditLog.operated_by == User.user_id)
    if table_name:
        stmt = stmt.where(AuditLog.table_name == table_name)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if operated_by:
        stmt = stmt.where(User.username == operated_by)
    if start:
        stmt = stmt.where(AuditLog.operated_at >= start)
    if end:
        stmt = stmt.where(AuditLog.operated_at <= end)

    # Historical before/after remains honest at rest. Current root restrictions
    # apply before selecting any audit payload, even for administrator readers.
    from app.services.capa_d4_material import root_metadata, authorize_root
    coordinates = (await db.execute(stmt.with_only_columns(
        AuditLog.log_id, AuditLog.table_name, AuditLog.record_id)
        .order_by(AuditLog.operated_at.desc(), AuditLog.log_id.desc())
        .limit(page_size).offset((page - 1) * page_size))).all()
    capa_ids = {record_id for _, table, record_id in coordinates if table == 'capa_eightd'}
    page_ids = [log_id for log_id, _, _ in coordinates]
    async def authorize_audits():
        for report_id in capa_ids:
            _, sources = await root_metadata(db, report_id)
            if sources:
                if actor_id is None:
                    raise PermissionError('D4_MATERIAL_UNAVAILABLE')
                await authorize_root(db, actor_id, report_id)
    await authorize_audits()
    total = (await db.execute(select(func.count()).select_from(
        stmt.with_only_columns(AuditLog.log_id).subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.where(AuditLog.log_id.in_(page_ids)).order_by(AuditLog.operated_at.desc(), AuditLog.log_id.desc())
    )).all()

    items = []
    for log in rows:
        items.append({
            "log_id": str(log.log_id),
            "table_name": log.table_name,
            "record_id": str(log.record_id),
            "action": log.action,
            "operated_by": log.username,
            "ip_address": log.ip_address,
            "operated_at": log.operated_at.isoformat() if log.operated_at else None,
            "changed_fields": log.changed_fields,
            "old_values": log.old_values,
            "new_values": log.new_values,
        })
    await authorize_audits()
    return items, total


async def list_login_logs(db: AsyncSession, filters: dict[str, Any], page: int, page_size: int):
    username = filters.get("username")
    success = filters.get("success")
    start, end = _bounds(filters)

    stmt = select(LoginAuditLog)
    if username:
        stmt = stmt.where(LoginAuditLog.username == username)
    if success is not None:
        stmt = stmt.where(LoginAuditLog.success == success)
    if start:
        stmt = stmt.where(LoginAuditLog.occurred_at >= start)
    if end:
        stmt = stmt.where(LoginAuditLog.occurred_at <= end)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(LoginAuditLog.occurred_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )).scalars().all()

    items = [{
        "log_id": str(r.log_id),
        "username": r.username,
        "user_id": str(r.user_id) if r.user_id else None,
        "success": r.success,
        "failure_reason": r.failure_reason,
        "ip_address": r.ip_address,
        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
    } for r in rows]
    return items, total


async def list_system_logs(db: AsyncSession, filters: dict[str, Any], page: int, page_size: int):
    level = filters.get("level")
    logger_name = filters.get("logger_name")
    start, end = _bounds(filters)

    stmt = select(SystemLog)
    if level:
        stmt = stmt.where(SystemLog.level == level)
    if logger_name:
        stmt = stmt.where(SystemLog.logger_name == logger_name)
    if start:
        stmt = stmt.where(SystemLog.occurred_at >= start)
    if end:
        stmt = stmt.where(SystemLog.occurred_at <= end)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(SystemLog.occurred_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )).scalars().all()

    items = [{
        "log_id": str(r.log_id),
        "logger_name": r.logger_name,
        "level": r.level,
        "message": r.message,
        "module": r.module,
        "traceback": r.traceback,
        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
    } for r in rows]
    return items, total
