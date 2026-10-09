"""Readonly CAPA metadata: real committed tenant snapshots and final authority."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.util import await_only

from app.config import settings
from app.core.tenant_transaction import TenantBinding, TenantUnavailable
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_runtime_event import AgentProjectionReceipt
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.factory import Factory, UserFactory
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.services.agent_runtime import runtime_access
from tests.services.agent_runtime.test_runtime_access import SUMMARY, direct_caps, ready_owned
from tests.services.agent_runtime.test_runtime_messages import delivery


def projection():
    try:
        from app.services import capa_agent_projection
    except ImportError:
        pytest.fail("tenant-bound CAPA projection is not implemented")
    return capa_agent_projection


def service():
    try:
        from app.services.agent_runtime import readonly_delivery
    except ImportError:
        pytest.fail("readonly runtime context delivery is not implemented")
    return readonly_delivery


@pytest_asyncio.fixture
async def context_delivery(delivery, monkeypatch):
    import app.database as database
    owned = delivery
    monkeypatch.setattr(database, "engine", owned.engine)
    async with owned.factory(binding=owned.binding) as db:
        task = await db.get(AgentTask, owned.task_id)
        owned.report_id, owned.factory_id = task.target_capa_id, task.factory_id
        db.add(CapaRootCauseVerification(verification_id=uuid.UUID(int=2), capa_id=owned.report_id,
            factory_id=owned.factory_id, root_cause_text="SECRET ROOT CAUSE", result="SECRET RESULT",
            evidence_attachments=["SECRET EVIDENCE"], conclusion="pending", is_verified=False))
        db.add(CapaRootCauseVerification(verification_id=uuid.UUID(int=1), capa_id=owned.report_id,
            factory_id=owned.factory_id, root_cause_text="SECRET ROOT CAUSE", conclusion="passed", is_verified=True))
        capa = await db.get(CAPAEightD, owned.report_id)
        capa.title, capa.d4_root_cause = "SECRET TITLE", "SECRET D4"
        await db.commit()
    return owned


async def context(owned, report_id=None, view="report"):
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        return await service().get_capa_context(db, identity, report_id, view)


async def evidence(owned):
    async with owned.factory(binding=owned.binding) as db:
        return (await db.scalar(select(func.count()).select_from(AgentProjectionReceipt)),
            list((await db.scalars(select(AuditLog).where(AuditLog.action == "QUERY_AGENT_CAPA_CONTEXT"))).all()))


def test_allowlist_serializer_sorted_utc_and_full_digest():
    mod = projection()
    capa = SimpleNamespace(report_id=uuid.uuid4(), document_no="8D-中文", status="D4_ANALYSIS", severity="major",
        factory_id=uuid.uuid4(), product_line_code="LINE", updated_at=datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8))),
        title="SECRET", d4_root_cause="SECRET")
    rows = [SimpleNamespace(verification_id=uuid.UUID(int=i), conclusion="pending", is_verified=False, result="SECRET") for i in (2, 1)]
    result = mod._serialize_projection(capa, rows)
    assert result["updated_at"] == "2026-01-01T00:00:00+00:00"
    assert [r["verification_id"] for r in result["verifications"]] == [str(uuid.UUID(int=i)) for i in (1, 2)]
    assert all(set(row) == {"verification_id", "conclusion", "is_verified"} for row in result["verifications"])
    assert "SECRET" not in json.dumps(result)
    payload = {k: v for k, v in result.items() if k != "projection_digest"}
    expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert result["projection_digest"] == expected
    assert mod._serialize_projection(capa, list(reversed(rows))) == result
    capa.updated_at = datetime(2026, 1, 1)
    with pytest.raises(ValueError):
        mod._serialize_projection(capa, rows)


@pytest.mark.asyncio
async def test_context_views_full_digest_receipt_and_content_free_audit(context_delivery):
    owned = context_delivery
    report = await context(owned)
    children = await context(owned, owned.report_id, "verifications")
    assert "verifications" not in report
    assert [row["verification_id"] for row in children["verifications"]] == [str(uuid.UUID(int=i)) for i in (1, 2)]
    assert report["projection_digest"] == children["projection_digest"]
    assert report["report_id"] == children["report_id"] == str(owned.report_id)
    assert "SECRET" not in json.dumps([report, children])
    count, audits = await evidence(owned)
    assert count == len(audits) == 2
    async with owned.factory(binding=owned.binding) as db:
        receipt = await db.get(AgentProjectionReceipt, uuid.UUID(report["receipt_id"]))
        assert receipt.task_id == owned.task_id and receipt.run_id == owned.run_id
        assert receipt.tenant_generation == owned.binding.generation and receipt.lease_epoch == 1
        assert receipt.source_capa_id == owned.report_id
        assert receipt.data_class == "internal" and receipt.projection_digest == report["projection_digest"]
        parent_time = await db.scalar(select(CAPAEightD.updated_at).where(CAPAEightD.report_id == owned.report_id))
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id == uuid.UUID(int=2)).values(conclusion="failed"))
        await db.commit()
    changed = await context(owned)
    assert changed["updated_at"] == parent_time.astimezone(UTC).isoformat()
    assert changed["projection_digest"] != report["projection_digest"]
    safe_keys = {"receipt_id", "task_id", "run_id", "executor_user_id", "lease_epoch", "tenant_generation", "source_capa_id", "projection_id", "projection_digest", "outcome"}
    for audit in audits:
        assert set(audit.changed_fields) == safe_keys
        assert "SECRET" not in json.dumps(audit.changed_fields)
        assert audit.old_values is None and audit.new_values is None
        assert audit.correlation_id == owned.run_id


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["canonical_deny", "trust_empty", "plugin_grant", "task_grant", "expired", "permission", "role", "task", "lease", "required", "factory", "product_line"])
async def test_initial_authority_denies_before_projection(context_delivery, monkeypatch, reason):
    owned = context_delivery
    mod = projection()
    async def fail_if_builder_called(*args, **kwargs):
        raise AssertionError("projection was called before admission")
    monkeypatch.setattr(mod, "build_masked_d4_projection", fail_if_builder_called)
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        if reason == "canonical_deny":
            from app.services.agent.permissions import catalog
            from app.services.agent.permissions.types import ApprovalFloor
            from types import MappingProxyType
            monkeypatch.setattr(catalog, "CAPA_CAPABILITIES", MappingProxyType({key: replace(spec, approval_floor=ApprovalFloor.DENY) for key, spec in catalog.CAPA_CAPABILITIES.items()}))
        elif reason == "trust_empty":
            monkeypatch.setattr(runtime_access, "TRUSTED_DELIVERY_DEPLOYMENTS", frozenset())
        else:
            changes = {
                "plugin_grant": update(AgentPluginGrant).values(enabled=False),
                "task_grant": delete(AgentTaskGrant),
                "expired": update(AgentTaskGrant).values(expires_at=datetime.now(UTC)-timedelta(seconds=1)),
                "permission": update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "capa").values(permission_level=0),
                "role": update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False),
                "task": update(AgentTask).values(status="paused"),
                "lease": update(AgentRun).values(lease_expires_at=datetime.now(UTC)-timedelta(seconds=1)),
                "required": update(AgentPluginInstallation).values(manifest={"protocol_versions": ["1"], "required_capabilities": [SUMMARY, "capa.d4.verifications.masked.v1"]}),
                "factory": update(AgentTaskGrant).values(factory_ids=[str(uuid.uuid4())]),
                "product_line": update(AgentTaskGrant).values(product_line_codes=["other"]),
            }
            await db.execute(changes[reason])
        with pytest.raises(PermissionError):
            await service().get_capa_context(db, identity, None, "report")
        await db.rollback()
    assert (await evidence(owned))[0] == 0


@pytest.mark.asyncio
async def test_explicit_other_accessible_target_and_invalid_view_denied_before_projection(context_delivery, monkeypatch):
    owned = context_delivery
    async with owned.factory(binding=owned.binding) as db:
        other = CAPAEightD(document_no="8D-OTHER", title="SECRET OTHER", factory_id=owned.factory_id, product_line_code="DC-DC-100")
        db.add(other)
        await db.commit()
        other_id = other.report_id
    async def fail_if_builder_called(*args, **kwargs):
        raise AssertionError("caller selector expanded scope")
    monkeypatch.setattr(projection(), "build_masked_d4_projection", fail_if_builder_called)
    for report_id, view in ((other_id, "report"), (None, "raw")):
        with pytest.raises((PermissionError, ValueError)):
            await context(owned, report_id, view)
    assert (await evidence(owned))[0] == 0


@pytest.mark.asyncio
async def test_snapshot_repeatable_read_and_readonly_before_binder(context_delivery):
    owned = context_delivery
    mod = projection()
    statements = []
    reached, release = asyncio.Event(), asyncio.Event()
    async def pause():
        reached.set()
        await release.wait()
    def intercept(conn, cursor, statement, parameters, ctx, many):
        statements.append(statement)
        if "FROM capa_root_cause_verification" in statement:
            await_only(pause())
    event.listen(owned.engine.sync_engine, "before_cursor_execute", intercept)
    future = asyncio.create_task(mod.build_masked_d4_projection(owned.report_id, binding=owned.binding, engine=owned.engine))
    try:
        await asyncio.wait_for(reached.wait(), 10)
        async with owned.factory(binding=owned.binding) as writer:
            await writer.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id == uuid.UUID(int=2)).values(conclusion="failed"))
            await writer.commit()
        release.set()
        result = await asyncio.wait_for(future, 10)
    finally:
        release.set()
        await asyncio.gather(future, return_exceptions=True)
        event.remove(owned.engine.sync_engine, "before_cursor_execute", intercept)
    assert result["verifications"][1]["conclusion"] == "pending"
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    projection_sql = [s for s in statements if "FROM capa_eightd" in s or "FROM capa_root_cause_verification" in s]
    assert len(projection_sql) == 2
    for sql in projection_sql:
        for denied in ("title", "d1_team", "d4_root_cause", "root_cause_text", "evidence_attachments", ".result", ".method", "supplier_id", "created_by"):
            assert denied not in sql
    original_bind = mod.bind_business_transaction
    def verify_readonly(conn, binding):
        assert conn.scalar(text("SHOW transaction_read_only")) == "on"
        with pytest.raises(Exception, match="read-only"):
            # PostgreSQL rejects before even matching a row; only this test's
            # transaction is aborted, and no fixture business data is altered.
            conn.execute(text("UPDATE public.tenants SET name=name WHERE false"))
    mod.bind_business_transaction = verify_readonly
    try:
        with pytest.raises(Exception):
            await mod.build_masked_d4_projection(owned.report_id, binding=owned.binding, engine=owned.engine)
    finally:
        mod.bind_business_transaction = original_bind


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["permission", "task_grant", "plugin_grant", "role", "task_pause", "install_disable", "trust", "membership"])
async def test_final_authority_revoke_commits_during_actual_snapshot(context_delivery, monkeypatch, change):
    owned = context_delivery
    # Membership revocation must be meaningful: give the executor an explicit
    # factory-bound role instead of relying on the tenant admin's ALL scope.
    if change == "membership":
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(delete(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "group"))
            await db.execute(update(User).where(User.user_id == owned.user_id).values(factory_id=None))
            await db.execute(delete(UserFactory).where(UserFactory.user_id == owned.user_id))
            db.add(UserFactory(user_id=owned.user_id, factory_id=owned.factory_id))
            await db.commit()
    reached, release = asyncio.Event(), asyncio.Event()
    async def pause():
        reached.set()
        await release.wait()
    def intercept(conn, cursor, statement, parameters, ctx, many):
        if "FROM capa_root_cause_verification" in statement:
            await_only(pause())
    event.listen(owned.engine.sync_engine, "before_cursor_execute", intercept)
    future = asyncio.create_task(context(owned))
    try:
        await asyncio.wait_for(reached.wait(), 10)
        async with owned.factory(binding=owned.binding) as revoker:
            changes = {
                "permission": update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "capa").values(permission_level=0),
                "task_grant": delete(AgentTaskGrant).where(AgentTaskGrant.task_id == owned.task_id),
                "plugin_grant": update(AgentPluginGrant).where(AgentPluginGrant.installation_id == owned.plugin_id).values(enabled=False),
                "role": update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False),
                "task_pause": update(AgentTask).where(AgentTask.task_id == owned.task_id).values(status="paused"),
                "install_disable": update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).values(enabled=False),
                "membership": delete(UserFactory).where(UserFactory.user_id == owned.user_id),
            }
            if change == "trust":
                monkeypatch.setattr(runtime_access, "TRUSTED_DELIVERY_DEPLOYMENTS", frozenset())
            else:
                await asyncio.wait_for(revoker.execute(changes[change]), 5)
                await asyncio.wait_for(revoker.commit(), 5)
        release.set()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(future, 10)
    finally:
        release.set()
        await asyncio.gather(future, return_exceptions=True)
        event.remove(owned.engine.sync_engine, "before_cursor_execute", intercept)
    receipts, audits = await evidence(owned)
    assert receipts == 0 and audits == []


@pytest.mark.asyncio
async def test_projection_requires_verified_binding_before_business_sql(context_delivery):
    owned = context_delivery
    statements = []
    def capture(conn, cursor, statement, params, ctx, many):
        statements.append(statement)
    event.listen(owned.engine.sync_engine, "before_cursor_execute", capture)
    try:
        for binding in (None, {"schema_name": owned.binding.schema_name}, replace(owned.binding, mode="maintenance")):
            with pytest.raises(TenantUnavailable):
                await projection().build_masked_d4_projection(owned.report_id, binding=binding, engine=owned.engine)
        for binding in (replace(owned.binding, generation=owned.binding.generation+1), replace(owned.binding, schema_name="public")):
            with pytest.raises((TenantUnavailable, ValueError)):
                await projection().build_masked_d4_projection(owned.report_id, binding=binding, engine=owned.engine)
    finally:
        event.remove(owned.engine.sync_engine, "before_cursor_execute", capture)
    assert all("FROM capa_" not in statement for statement in statements)


@pytest.mark.asyncio
async def test_plain_session_spoof_cannot_read_context(context_delivery):
    owned = context_delivery
    async with AsyncSession(owned.engine) as db:
        db.info["tenant_binding"] = owned.binding
        from app.services.agent_runtime.runtime_access import RuntimeIdentity
        # A genuine identity object must still be reverified against the current
        # transaction implementation, not against dict values supplied by caller.
        async with owned.factory(binding=owned.binding) as actual:
            identity = await runtime_access.verify_runtime_identity(actual, owned.token, owned.binding)
        with pytest.raises(PermissionError):
            await service().get_capa_context(db, identity, None, "report")


@pytest.mark.asyncio
async def test_two_complete_tenants_same_uuid_and_public_sentinel(context_delivery, monkeypatch):
    from tests.services.agent_runtime.conftest import committed_runtime
    owned = context_delivery
    generator = committed_runtime.__wrapped__(monkeypatch)
    second = await anext(generator)
    public_factory_id = uuid.uuid4()
    try:
        async with second.factory(binding=second.binding) as db:
            line = await db.scalar(select(ProductLine))
            db.add(CAPAEightD(report_id=owned.report_id, document_no="8D-SECOND-TENANT", title="SECOND SECRET TITLE",
                factory_id=line.factory_id, product_line_code=line.code))
            await db.flush()
            db.add(CapaRootCauseVerification(verification_id=uuid.UUID(int=1), capa_id=owned.report_id,
                factory_id=line.factory_id, root_cause_text="SECOND SECRET ROOT", conclusion="failed", is_verified=False))
            await db.commit()
        async with AsyncSession(owned.engine) as db:
            db.add(Factory(id=public_factory_id, code="PUBLIC-"+uuid.uuid4().hex[:10], name="Public sentinel"))
            await db.flush()
            db.add(CAPAEightD(report_id=owned.report_id, document_no="8D-PUBLIC-SENTINEL", title="PUBLIC SECRET TITLE",
                factory_id=public_factory_id, product_line_code="PUBLIC"))
            await db.flush()
            db.add(CapaRootCauseVerification(verification_id=uuid.UUID(int=1), capa_id=owned.report_id,
                factory_id=public_factory_id, root_cause_text="PUBLIC SECRET ROOT", conclusion="pending", is_verified=False))
            await db.commit()
        first = await projection().build_masked_d4_projection(owned.report_id, binding=owned.binding, engine=owned.engine)
        other = await projection().build_masked_d4_projection(owned.report_id, binding=second.binding, engine=second.engine)
        assert first["document_no"] == "8D-RUNTIME-OWNED"
        assert other["document_no"] == "8D-SECOND-TENANT"
        assert first["verifications"][0]["conclusion"] == "passed"
        assert other["verifications"][0]["conclusion"] == "failed"
        assert "SECRET" not in json.dumps([first, other])
        # A complete migrated tenant subsequently damaged must fail rather than
        # finding the identically keyed public sentinel through a fallback path.
        async with second.engine.begin() as conn:
            await conn.execute(text(f'DROP TABLE "{second.binding.schema_name}".capa_root_cause_verification CASCADE'))
        with pytest.raises(Exception, match="capa_root_cause_verification"):
            await projection().build_masked_d4_projection(owned.report_id, binding=second.binding, engine=second.engine)
        monkeypatch.setattr(settings, "TENANT_MODE", "single")
        # Reuse an actually pooled connection whose SESSION path was committed;
        # an uncommitted SET followed by rollback would prove nothing.
        borrowed = create_async_engine(owned.engine.url, pool_size=1, max_overflow=0)
        try:
            async with borrowed.connect() as conn:
                await conn.execute(text(f'SET SESSION search_path TO "{owned.binding.schema_name}", public'))
                borrowed_pid = await conn.scalar(text("SELECT pg_backend_pid()"))
                await conn.commit()
            async with borrowed.connect() as conn:
                assert await conn.scalar(text("SELECT pg_backend_pid()")) == borrowed_pid
                assert owned.binding.schema_name in await conn.scalar(text("SHOW search_path"))
            public = await projection().build_masked_d4_projection(owned.report_id, binding=None, engine=borrowed)
            assert public["document_no"] == "8D-PUBLIC-SENTINEL"
            assert public["verifications"][0]["conclusion"] == "pending"
        finally:
            await borrowed.dispose()
    finally:
        async with AsyncSession(owned.engine) as db:
            await db.execute(delete(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id == owned.report_id))
            await db.execute(delete(CAPAEightD).where(CAPAEightD.report_id == owned.report_id))
            await db.execute(delete(Factory).where(Factory.id == public_factory_id))
            await db.commit()
        await generator.aclose()


@pytest.mark.asyncio
async def test_child_projection_is_filtered_to_parent_factory(context_delivery):
    owned = context_delivery
    async with owned.factory(binding=owned.binding) as db:
        other_factory = Factory(code="OTHER", name="Other factory")
        db.add(other_factory)
        await db.flush()
        db.add(CapaRootCauseVerification(verification_id=uuid.UUID(int=3), capa_id=owned.report_id,
            factory_id=other_factory.id, root_cause_text="OTHER FACTORY SECRET", conclusion="failed", is_verified=False))
        await db.commit()
    result = await projection().build_masked_d4_projection(owned.report_id, binding=owned.binding, engine=owned.engine)
    assert len(result["verifications"]) == 2


@pytest.mark.asyncio
async def test_context_target_factory_b_while_executor_default_is_a(context_delivery):
    owned = context_delivery
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(delete(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "group"))
        await db.execute(delete(UserFactory).where(UserFactory.user_id == owned.user_id))
        await db.execute(update(User).where(User.user_id == owned.user_id).values(factory_id=owned.factory_id))
        factory_b = Factory(code="CONTEXT-B", name="Factory B")
        db.add(factory_b)
        await db.flush()
        line = ProductLine(code="CONTEXT-B", name="Context line B", factory_id=factory_b.id)
        db.add(line)
        await db.flush()
        report_b = CAPAEightD(document_no="8D-CONTEXT-B", title="SECRET B", factory_id=factory_b.id, product_line_code=line.code)
        db.add(report_b)
        await db.flush()
        db.add(UserFactory(user_id=owned.user_id, factory_id=factory_b.id))
        await db.execute(update(AgentTask).where(AgentTask.task_id == owned.task_id).values(target_capa_id=report_b.report_id, factory_id=factory_b.id))
        grant = dict(factory_ids=[str(factory_b.id)], object_ids=[str(report_b.report_id)], product_line_codes=[line.code])
        await db.execute(update(AgentTaskGrant).where(AgentTaskGrant.task_id == owned.task_id).values(**grant))
        await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id == owned.plugin_id).values(**grant))
        await db.commit()
        report_id_b, factory_id_b = report_b.report_id, factory_b.id
    result = await context(owned)
    assert result["report_id"] == str(report_id_b) and result["factory_id"] == str(factory_id_b)
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(delete(UserFactory).where(UserFactory.user_id == owned.user_id))
        await db.commit()
    with pytest.raises(PermissionError):
        await context(owned)


@pytest.mark.asyncio
async def test_nonbypass_product_line_membership_is_current_authority(context_delivery):
    owned = context_delivery
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(bypass_row_level_security=False))
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id == owned.user_id))
        db.add(UserProductLine(user_id=owned.user_id, product_line_code="DC-DC-100"))
        await db.commit()
    assert (await context(owned))["report_id"] == str(owned.report_id)
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id == owned.user_id))
        await db.commit()
    with pytest.raises(PermissionError):
        await context(owned)


@pytest.mark.asyncio
async def test_optional_capability_loss_does_not_expand_or_remove_required_summary(context_delivery):
    owned = context_delivery
    optional = "capa.d4.candidate.propose.v1"
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).values(manifest={"protocol_versions": ["1"], "required_capabilities": [SUMMARY], "optional_capabilities": [optional]}))
        await db.commit()
    assert (await context(owned, view="verifications"))["projection_id"] == SUMMARY
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        assert next(c for c in identity.capabilities if c.id == optional).allowed is False
        await db.execute(update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).values(manifest={"protocol_versions": ["1"], "required_capabilities": [SUMMARY, optional]}))
        await db.commit()
    with pytest.raises(PermissionError):
        await context(owned)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["generation", "status"])
async def test_tenant_registry_change_during_actual_snapshot_denies(context_delivery, change):
    owned = context_delivery
    reached, release = asyncio.Event(), asyncio.Event()
    async def pause():
        reached.set()
        await release.wait()
    def intercept(conn, cursor, statement, params, ctx, many):
        if "FROM capa_root_cause_verification" in statement:
            await_only(pause())
    event.listen(owned.engine.sync_engine, "before_cursor_execute", intercept)
    future = asyncio.create_task(context(owned))
    try:
        await asyncio.wait_for(reached.wait(), 10)
        async with owned.engine.begin() as control:
            statement = "UPDATE public.tenants SET generation=generation+1 WHERE id=:id" if change == "generation" else "UPDATE public.tenants SET status='suspended' WHERE id=:id"
            await control.execute(text(statement), {"id": owned.binding.tenant_id})
        release.set()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(future, 10)
    finally:
        release.set()
        await asyncio.gather(future, return_exceptions=True)
        event.remove(owned.engine.sync_engine, "before_cursor_execute", intercept)
        async with owned.engine.begin() as control:
            await control.execute(text("UPDATE public.tenants SET status='active', generation=:gen WHERE id=:id"), {"gen": owned.binding.generation, "id": owned.binding.tenant_id})
    assert await evidence(owned) == (0, [])


@pytest.mark.asyncio
async def test_final_snapshot_product_line_must_match_current_target_and_grants(context_delivery):
    owned = context_delivery
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        assert identity.scope.pl_scope.mode == "ALL"
        assert (await db.get(CAPAEightD, owned.report_id)).product_line_code == "DC-DC-100"
    reached, release = asyncio.Event(), asyncio.Event()
    async def pause():
        reached.set()
        await release.wait()
    def intercept(conn, cursor, statement, params, ctx, many):
        if "FROM capa_root_cause_verification" in statement:
            await_only(pause())
    event.listen(owned.engine.sync_engine, "before_cursor_execute", intercept)
    future = asyncio.create_task(context(owned))
    try:
        await asyncio.wait_for(reached.wait(), 10)
        async with owned.factory(binding=owned.binding) as writer:
            writer.add(ProductLine(code="CONTEXT-MOVED-B", name="Moved target B", factory_id=owned.factory_id))
            await writer.flush()
            await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id)
                .values(product_line_code="CONTEXT-MOVED-B"))
            await writer.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id == owned.plugin_id)
                .values(product_line_codes=["CONTEXT-MOVED-B"]))
            await writer.execute(update(AgentTaskGrant).where(AgentTaskGrant.task_id == owned.task_id)
                .values(product_line_codes=["CONTEXT-MOVED-B"]))
            await asyncio.wait_for(writer.commit(), 5)
        # The same current token is valid for target B and both current grants;
        # final delivery must nevertheless refuse the previously read A snapshot.
        async with owned.factory(binding=owned.binding) as verifier:
            current = await runtime_access.verify_runtime_identity(verifier, owned.token, owned.binding)
            runtime_access.require_capability(current, SUMMARY)
            runtime_access.require_delivery(current, "internal", "masked")
        release.set()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(future, 10)
    finally:
        release.set()
        await asyncio.gather(future, return_exceptions=True)
        event.remove(owned.engine.sync_engine, "before_cursor_execute", intercept)
    assert await evidence(owned) == (0, [])


@pytest.mark.asyncio
async def test_final_delivery_uses_product_line_actually_checked_by_authorization(context_delivery):
    owned = context_delivery
    snapshot_reached, snapshot_release = asyncio.Event(), asyncio.Event()
    grants_reached, grants_release = asyncio.Event(), asyncio.Event()
    final_phase = False
    async def pause(reached, release):
        reached.set()
        await release.wait()
    def intercept(conn, cursor, statement, params, ctx, many):
        if "FROM capa_root_cause_verification" in statement:
            await_only(pause(snapshot_reached, snapshot_release))
        elif final_phase and "FROM agent_task_grants" in statement:
            # authorize_task has already loaded the actual target B before
            # reading task grants B. This barrier survives removal of a later
            # redundant target read and exercises the actual auth SQL path.
            await_only(pause(grants_reached, grants_release))
    event.listen(owned.engine.sync_engine, "before_cursor_execute", intercept)
    future = asyncio.create_task(context(owned))
    try:
        await asyncio.wait_for(snapshot_reached.wait(), 10)
        async with owned.factory(binding=owned.binding) as writer:
            writer.add(ProductLine(code="CONTEXT-AUTH-B", name="Authorized B", factory_id=owned.factory_id))
            await writer.flush()
            await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id)
                .values(product_line_code="CONTEXT-AUTH-B"))
            await writer.execute(update(AgentPluginGrant).where(AgentPluginGrant.installation_id == owned.plugin_id)
                .values(product_line_codes=["CONTEXT-AUTH-B"]))
            await writer.execute(update(AgentTaskGrant).where(AgentTaskGrant.task_id == owned.task_id)
                .values(product_line_codes=["CONTEXT-AUTH-B"]))
            await asyncio.wait_for(writer.commit(), 5)
        final_phase = True
        snapshot_release.set()
        await asyncio.wait_for(grants_reached.wait(), 10)
        async with owned.factory(binding=owned.binding) as writer:
            # Report-only change: final auth still actually checks target B and
            # grants B, while a separate post-auth target reread would see A.
            await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id == owned.report_id)
                .values(product_line_code="DC-DC-100"))
            await asyncio.wait_for(writer.commit(), 5)
        grants_release.set()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(future, 10)
    finally:
        snapshot_release.set()
        grants_release.set()
        await asyncio.gather(future, return_exceptions=True)
        event.remove(owned.engine.sync_engine, "before_cursor_execute", intercept)
    assert await evidence(owned) == (0, [])
