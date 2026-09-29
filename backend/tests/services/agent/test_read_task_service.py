"""Fail-closed, single-report Agent read task lifecycle."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.config import settings
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import Module
from app.models.agent_read_task import AgentReadTask
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.role import RolePermission
from app.services.agent.read_task_service import create_read_task, check_read_task, revoke_read_task

pytestmark = pytest.mark.asyncio
CAPABILITY = "capa.d4.summary.masked.v1"


@pytest.fixture
def scope(admin_user, default_factory):
    return RequestScope(
        FactoryScope([default_factory.id], default_factory.id),
        default_factory.id,
        ProductLineScope("EXPLICIT", ["DC-DC-100"]),
        admin_user,
    )


@pytest.fixture
def capa(db, admin_user, default_factory):
    report = CAPAEightD(
        report_id=uuid4(), document_no=f"8D-{uuid4().hex[:12]}",
        title="private-title-marker", d4_root_cause="private-root-cause-marker",
        factory_id=default_factory.id, product_line_code="DC-DC-100",
        created_by=admin_user.user_id,
    )
    db.add(report)
    return report


async def _logs(db, task_id):
    return (await db.execute(select(AuditLog).where(
        AuditLog.table_name == "agent_read_tasks", AuditLog.record_id == task_id
    ).order_by(AuditLog.operated_at))).scalars().all()


async def test_create_and_check_issue_single_report_grant_with_safe_audit(db, scope, capa):
    await db.flush()
    task = await create_read_task(db, scope, capa.report_id)
    assert isinstance(task, AgentReadTask)
    assert task.initiator_user_id == scope.user.user_id
    assert task.tenant_schema == "public"
    assert task.capa_id == capa.report_id
    assert task.factory_id == capa.factory_id
    assert task.product_line_code == capa.product_line_code
    assert task.capability_id == CAPABILITY
    assert task.expires_at - task.created_at == timedelta(hours=24)
    grant = await check_read_task(db, scope, task.task_id, task.created_at)
    assert grant.capability_id == CAPABILITY
    assert grant.factory_ids == frozenset({capa.factory_id})
    assert grant.object_ids == frozenset({capa.report_id})
    assert grant.product_line_codes == frozenset({capa.product_line_code})
    assert grant.expires_at == task.expires_at
    logs = await _logs(db, task.task_id)
    assert {log.action for log in logs} == {"CREATE", "CHECK_ALLOW"}
    for log in logs:
        assert log.factory_id == capa.factory_id
        assert log.tenant_schema == "public"
        assert log.operated_by == scope.user.user_id
        assert set(log.changed_fields) == {"capability_id", "object_id", "expires_at", "status"}
        assert "private-title-marker" not in str(log.changed_fields)
        assert "private-root-cause-marker" not in str(log.changed_fields)
        assert log.old_values is None and log.new_values is None


async def test_check_denies_other_user_without_audit(db, scope, capa, other_admin_user):
    await db.flush()
    task = await create_read_task(db, scope, capa.report_id)
    other = replace(scope, user=other_admin_user)
    with pytest.raises((ValueError, LookupError)):
        await check_read_task(db, other, task.task_id, task.created_at)
    assert [x.action for x in await _logs(db, task.task_id)] == ["CREATE"]


@pytest.mark.parametrize("denial", ["factory", "product_line", "permission", "expired", "report_scope", "tenant", "capability", "revoked"])
async def test_check_denies_stale_or_out_of_scope_task(db, scope, capa, denial, monkeypatch):
    await db.flush()
    task = await create_read_task(db, scope, capa.report_id)
    now = task.created_at
    if denial == "factory":
        scope.effective_factory_id = uuid4()
    elif denial == "product_line":
        scope.pl_scope = ProductLineScope("EXPLICIT", ["OTHER"])
    elif denial == "permission":
        permission = (await db.execute(select(RolePermission).where(
            RolePermission.role_id == scope.user.role_id, RolePermission.module == Module.CAPA.value
        ))).scalar_one()
        permission.permission_level = 0
        await db.flush()
    elif denial == "expired":
        now = task.expires_at
    elif denial == "report_scope":
        capa.product_line_code = "OTHER"
        await db.flush()
    elif denial == "tenant":
        task.tenant_schema = "other"
        await db.flush()
    elif denial == "capability":
        # The DB constraint pins the ID; a missing catalog declaration also fails closed.
        monkeypatch.setattr("app.services.agent.read_task_service.get_capability", lambda _id: None)
    elif denial == "revoked":
        await revoke_read_task(db, scope, task.task_id)
    with pytest.raises((ValueError, LookupError)):
        await check_read_task(db, scope, task.task_id, now)
    denials = [x for x in await _logs(db, task.task_id) if x.action == "CHECK_DENY"]
    assert len(denials) == 1
    assert set(denials[0].changed_fields) == {"reason"}
    assert denials[0].old_values is None and denials[0].new_values is None


async def test_create_requires_current_permission_and_scope(db, scope, capa):
    await db.flush()
    scope.pl_scope = ProductLineScope("NONE", None)
    with pytest.raises((ValueError, LookupError)):
        await create_read_task(db, scope, capa.report_id)
    scope.pl_scope = ProductLineScope("ALL", None)
    scope.effective_factory_id = uuid4()
    with pytest.raises((ValueError, LookupError)):
        await create_read_task(db, scope, capa.report_id)
    scope.effective_factory_id = capa.factory_id
    permission = (await db.execute(select(RolePermission).where(
        RolePermission.role_id == scope.user.role_id, RolePermission.module == Module.CAPA.value
    ))).scalar_one()
    permission.permission_level = 0
    await db.flush()
    with pytest.raises((ValueError, LookupError)):
        await create_read_task(db, scope, capa.report_id)


async def test_revoke_is_idempotent_and_owner_bound(db, scope, capa, other_admin_user):
    await db.flush()
    task = await create_read_task(db, scope, capa.report_id)
    with pytest.raises((ValueError, LookupError)):
        await revoke_read_task(db, replace(scope, user=other_admin_user), task.task_id)
    await revoke_read_task(db, scope, task.task_id)
    first = task.revoked_at
    await revoke_read_task(db, scope, task.task_id)
    assert task.status == "revoked"
    assert task.revoked_at == first
    revocations = [x for x in await _logs(db, task.task_id) if x.action == "REVOKE"]
    assert len(revocations) == 1
    assert set(revocations[0].changed_fields) == {"capability_id", "object_id", "expires_at", "status"}


@pytest.mark.parametrize("mode", ["dev", "production"])
async def test_unsupported_tenant_mode_denies_before_any_query(db, scope, monkeypatch, mode):
    monkeypatch.setattr(settings, "TENANT_MODE", mode)
    class NoQuery:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("queried before tenant mode check")
    no_query = NoQuery()
    for operation in (
        lambda: create_read_task(no_query, scope, uuid4()),
        lambda: check_read_task(no_query, scope, uuid4(), datetime.now(UTC)),
        lambda: revoke_read_task(no_query, scope, uuid4()),
    ):
        with pytest.raises(ValueError):
            await operation()
