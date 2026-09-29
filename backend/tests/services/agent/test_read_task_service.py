"""Fail-closed, single-report Agent read task lifecycle."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.config import settings
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import Module
from app.models.agent_read_task import AgentReadTask
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
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


@pytest_asyncio.fixture
async def committed_task(sessionmaker):
    """A task whose dependencies are committed and visible to independent sessions."""
    factory_id, role_id, user_id, report_id = (uuid4() for _ in range(4))
    token = uuid4().hex[:12]
    async with sessionmaker() as setup:
        setup.add(Factory(id=factory_id, code=f"RT-{token}", name="Read task factory"))
        setup.add(RoleDefinition(
            id=role_id, role_key=f"rt_{token}", name_zh="测试", name_en="Read Task Test",
            is_system=False, is_active=True,
        ))
        await setup.flush()
        setup.add(RolePermission(role_id=role_id, module=Module.CAPA.value, permission_level=1))
        user = User(
            user_id=user_id, username=f"read_task_{token}", password_hash="hashed",
            role_id=role_id, legacy_role="viewer", is_active=True, factory_id=factory_id,
        )
        setup.add(user)
        await setup.flush()
        setup.add(CAPAEightD(
            report_id=report_id, document_no=f"8D-RT-{token}", title="Concurrent read task",
            factory_id=factory_id, product_line_code="DC-DC-100", created_by=user_id,
        ))
        await setup.commit()
        scope = RequestScope(
            FactoryScope([factory_id], factory_id), factory_id,
            ProductLineScope("EXPLICIT", ["DC-DC-100"]), user,
        )
        task = await create_read_task(setup, scope, report_id)
        task_id = task.task_id
        check_time = task.created_at
    try:
        yield scope, task_id, report_id, check_time
    finally:
        async with sessionmaker() as cleanup:
            await cleanup.execute(delete(AuditLog).where(
                AuditLog.table_name == "agent_read_tasks", AuditLog.record_id == task_id,
            ))
            await cleanup.execute(delete(AgentReadTask).where(AgentReadTask.task_id == task_id))
            await cleanup.execute(delete(CAPAEightD).where(CAPAEightD.report_id == report_id))
            await cleanup.execute(delete(User).where(User.user_id == user_id))
            await cleanup.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
            await cleanup.execute(delete(RoleDefinition).where(RoleDefinition.id == role_id))
            await cleanup.execute(delete(Factory).where(Factory.id == factory_id))
            await cleanup.commit()


@pytest.mark.parametrize("change", ["revoke", "report_scope"])
async def test_check_reloads_committed_state_after_session_cache_warmed(sessionmaker, committed_task, change):
    scope, task_id, report_id, check_time = committed_task
    async with sessionmaker() as reader:
        cached_task = await reader.get(AgentReadTask, task_id)
        cached_report = await reader.get(CAPAEightD, report_id)
        assert cached_task.status == "active"
        assert cached_report.product_line_code == "DC-DC-100"
        await reader.commit()  # Keep the identity map, release the old DB snapshot.
        async with sessionmaker() as writer:
            if change == "revoke":
                await revoke_read_task(writer, scope, task_id)
            else:
                report = await writer.get(CAPAEightD, report_id)
                report.product_line_code = "OTHER"
                await writer.commit()
        with pytest.raises(ValueError) as exc:
            await check_read_task(reader, scope, task_id, check_time)
        assert str(exc.value) == (
            "Agent read task revoked" if change == "revoke" else "Agent read task denied"
        )


async def test_overlapping_revoke_transactions_write_one_audit(sessionmaker, committed_task):
    scope, task_id, _report_id, _check_time = committed_task
    async with sessionmaker() as first, sessionmaker() as second:
        first_cached = await first.get(AgentReadTask, task_id)
        second_cached = await second.get(AgentReadTask, task_id)
        assert first_cached.status == "active"
        assert second_cached.status == "active"
        await first.execute(select(AgentReadTask).where(
            AgentReadTask.task_id == task_id,
        ).with_for_update())
        pending = asyncio.create_task(revoke_read_task(second, scope, task_id))
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(pending), timeout=0.1)
            await revoke_read_task(first, scope, task_id)
            await asyncio.wait_for(pending, timeout=2)
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    async with sessionmaker() as verify:
        revocations = [log for log in await _logs(verify, task_id) if log.action == "REVOKE"]
        assert len(revocations) == 1


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
    with pytest.raises(ValueError) as exc:
        await check_read_task(db, scope, task.task_id, now)
    expected_message = {
        "expired": "Agent read task expired",
        "revoked": "Agent read task revoked",
    }.get(denial, "Agent read task denied")
    assert str(exc.value) == expected_message
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


@pytest.mark.parametrize("denial", ["missing", "permission", "factory", "product_line"])
async def test_create_does_not_reveal_report_existence(db, scope, capa, denial):
    await db.flush()
    capa_id = capa.report_id
    if denial == "missing":
        capa_id = uuid4()
    elif denial == "permission":
        permission = (await db.execute(select(RolePermission).where(
            RolePermission.role_id == scope.user.role_id, RolePermission.module == Module.CAPA.value
        ))).scalar_one()
        permission.permission_level = 0
        await db.flush()
    elif denial == "factory":
        scope.effective_factory_id = uuid4()
    elif denial == "product_line":
        scope.pl_scope = ProductLineScope("NONE", None)
    with pytest.raises(ValueError) as exc:
        await create_read_task(db, scope, capa_id)
    assert str(exc.value) == "CAPA unavailable"


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
