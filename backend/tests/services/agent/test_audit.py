import uuid

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.services.agent import audit


@pytest.mark.asyncio
async def test_write_audit_raw_writes_factory_tenant_correlation(db, admin_user, default_factory):
    corr = uuid.uuid4()
    rec = uuid.uuid4()
    log = await audit.write_audit_raw(
        db, user_id=admin_user.user_id, factory_id=default_factory.id,
        tenant_schema="public", table_name="quality_trends", record_id=rec,
        action="AI_TREND_INTERPRET", correlation_id=corr,
        new_values={"status": "success"},
    )
    got = (await db.execute(select(AuditLog).where(AuditLog.log_id == log.log_id))).scalar_one()
    assert got.factory_id == default_factory.id
    assert got.tenant_schema == "public"
    assert got.correlation_id == corr
    assert got.operated_by == admin_user.user_id
    assert got.new_values == {"status": "success"}


@pytest.mark.asyncio
async def test_write_audit_raw_accepts_none_factory(db, admin_user):
    """factory_id is nullable (None = global scope)."""
    log = await audit.write_audit_raw(
        db, user_id=admin_user.user_id, factory_id=None,
        tenant_schema="public", table_name="quality_trends",
        record_id=uuid.uuid4(), action="AI_TREND_INTERPRET",
    )
    assert log.factory_id is None


@pytest.mark.asyncio
async def test_write_audit_delegates_to_raw(db, admin_user, default_factory):
    """write_audit(ctx, ...) still works after refactor (P0 callers unchanged)."""
    from app.services.agent import harness
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    log = await audit.write_audit(db, ctx, "agent_tool_calls", uuid.uuid4(), "call", uuid.uuid4())
    assert log.factory_id == default_factory.id
    assert log.operated_by == admin_user.user_id
