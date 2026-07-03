"""Read-only paginated queries for audit / login / system logs (tenant-scoped)."""
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.login_audit_log import LoginAuditLog
from app.models.system_log import SystemLog
from app.models.user import User


def _bounds(filters: dict[str, Any]):
    start = filters.get("start")
    end = filters.get("end")
    return start, end


async def list_audit_logs(db: AsyncSession, filters: dict[str, Any], page: int, page_size: int):
    table_name = filters.get("table_name")
    action = filters.get("action")
    operated_by = filters.get("operated_by")  # username
    start, end = _bounds(filters)

    stmt = select(AuditLog, User.username).outerjoin(User, AuditLog.operated_by == User.user_id)
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

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(
        stmt.order_by(AuditLog.operated_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )).all()

    items = []
    for log, username in rows:
        items.append({
            "log_id": str(log.log_id),
            "table_name": log.table_name,
            "record_id": str(log.record_id),
            "action": log.action,
            "operated_by": username,
            "ip_address": log.ip_address,
            "operated_at": log.operated_at.isoformat() if log.operated_at else None,
            "changed_fields": log.changed_fields,
            "old_values": log.old_values,
            "new_values": log.new_values,
        })
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
