"""Recovery authority tests for scan-gated private task attachments.

The recovery implementation is deliberately loaded inside each test so this file
first proves that the public maintenance interface is absent, rather than
silently succeeding against an accidental import.
"""
from __future__ import annotations

import hashlib
import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import settings
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.tenant_transaction import TenantBinding
from app.database import TenantSession
from app.models.agent_task import AgentTask
from app.models.agent_task_attachment import AgentTaskAttachment
from app.models.capa import CAPAEightD
from app.models.product_line import ProductLine


def recovery_module():
    name = "app.services.agent_runtime.attachment_recovery"
    assert importlib.util.find_spec(name) is not None, "attachment recovery service is missing"
    return __import__(name, fromlist=["reconcile_live_namespace"])


def test_recovery_module_exposes_platform_authorized_reconciliation():
    recovery = recovery_module()
    assert callable(recovery.reconcile_live_namespace)
    assert callable(recovery.reconcile_disposed_namespace)

def test_maintenance_cli_accepts_only_the_fixed_reconcile_command():
    name = "app.cli.agent_task_attachments"
    assert importlib.util.find_spec(name) is not None, "attachment maintenance CLI is missing"
    cli = __import__(name, fromlist=["parser"])
    args = cli.parser().parse_args(["reconcile"])
    assert vars(args) == {"command": "reconcile"}


@pytest.mark.asyncio
async def test_startup_defers_when_a_live_attachment_pipeline_holds_the_lock(monkeypatch):
    """A live predecessor pipeline is not storage-integrity failure authority."""
    from app import main
    from app.config import settings
    from app.services.agent_runtime import attachment_recovery, task_attachments

    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)

    async def locked_reconciliation():
        raise task_attachments.AttachmentCapacityError("attachment pipeline is busy")

    monkeypatch.setattr(attachment_recovery, "reconcile_configured_storage", locked_reconciliation)
    async with main.lifespan(main.app):
        assert settings.AGENT_TASK_ATTACHMENTS_ENABLED is True


@pytest.fixture
def attachment_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_STORAGE_ROOT", str(tmp_path / "attachments"))
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_RETENTION_HOURS", 168)
    return tmp_path


@pytest_asyncio.fixture
async def owned_attachment(db, request_scope_all, sample_capa, enabled_plugin):
    scope = request_scope_all
    task = AgentTask(
        initiator_id=scope.user.user_id,
        executor_user_id=scope.user.user_id,
        preferred_installation_id=enabled_plugin.installation_id,
        target_capa_id=sample_capa.report_id,
        factory_id=sample_capa.factory_id,
        request_key=uuid.uuid4().hex,
        status="ready",
    )
    db.add(task)
    await db.flush()
    attachment = AgentTaskAttachment(
        task_id=task.task_id,
        factory_id=task.factory_id,
        uploaded_by=scope.user.user_id,
        tenant_id=None,
        origin_generation=None,
        storage_namespace="public",
        storage_key=uuid.uuid4().hex,
        byte_size=5,
        sha256=hashlib.sha256(b"clean").hexdigest(),
        status="promoting",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(attachment)
    await db.flush()
    return SimpleNamespace(db=db, scope=scope, task=task, attachment=attachment)


def _namespace(attachment):
    from app.services.agent_runtime.attachment_storage import AttachmentNamespace

    return AttachmentNamespace(
        tenant_id=attachment.tenant_id,
        origin_generation=attachment.origin_generation,
        storage_namespace=attachment.storage_namespace,
    )


def _storage():
    from app.services.agent_runtime.attachment_storage import PrivateAttachmentStorage

    return PrivateAttachmentStorage(Path(settings.AGENT_TASK_ATTACHMENT_STORAGE_ROOT))


def _write_clean_file(attachment):
    storage = _storage()
    with storage.create_staging(_namespace(attachment), attachment.attachment_id) as handle:
        handle.write(b"clean")
    storage.promote(_namespace(attachment), attachment.attachment_id, attachment.sha256, attachment.byte_size)
    return storage


@pytest.mark.asyncio
async def test_promoting_clean_file_after_crash_becomes_available(owned_attachment, attachment_settings):
    """Recovery may publish only the exact durable promoting row it verifies."""
    recovery = recovery_module()
    storage = _write_clean_file(owned_attachment.attachment)

    stats = await recovery.reconcile_live_namespace(
        owned_attachment.db,
        _namespace(owned_attachment.attachment),
        storage,
        now=datetime.now(UTC),
    )

    await owned_attachment.db.refresh(owned_attachment.attachment)
    assert stats.promoted == 1
    assert owned_attachment.attachment.status == "available"
    from app.services.agent_runtime.task_attachments import open_download

    handle = await open_download(
        owned_attachment.db,
        owned_attachment.scope,
        owned_attachment.task.task_id,
        owned_attachment.attachment.attachment_id,
    )
    try:
        assert handle.stream.read() == b"clean"
    finally:
        handle.stream.close()


@pytest.mark.asyncio
async def test_expired_scanning_and_purging_reconcile_without_owner_authority(
    owned_attachment, attachment_settings,
):
    """Maintenance must complete durable states without consulting uploaded_by."""
    recovery = recovery_module()
    attachment = owned_attachment.attachment
    attachment.status = "scanning"
    attachment.reservation_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    attachment.byte_size = None
    attachment.sha256 = None
    storage = _storage()
    with storage.create_staging(_namespace(attachment), attachment.attachment_id) as handle:
        handle.write(b"untrusted")
    await owned_attachment.db.commit()

    stats = await recovery.reconcile_live_namespace(
        owned_attachment.db, _namespace(attachment), storage, now=datetime.now(UTC),
    )
    await owned_attachment.db.refresh(attachment)
    assert stats.failed_scanning == 1
    assert attachment.status == "failed_storage"

    attachment.status = "purging"
    attachment.sha256 = hashlib.sha256(b"clean").hexdigest()
    attachment.byte_size = 5
    _write_clean_file(attachment)
    await owned_attachment.db.commit()
    stats = await recovery.reconcile_live_namespace(
        owned_attachment.db, _namespace(attachment), storage, now=datetime.now(UTC),
    )
    await owned_attachment.db.refresh(attachment)
    assert stats.purged == 1
    assert attachment.status == "purged"


@pytest.mark.asyncio
async def test_generation_increment_preserves_available_attachment(committed_runtime, attachment_settings):
    """A normal generation change is not disposal authority for old attachment bytes."""
    from app.services.agent_runtime import task_attachments

    runtime = committed_runtime
    old_binding = runtime.binding
    async with runtime.factory(binding=old_binding) as db:
        task = await db.get(AgentTask, runtime.task_id)
        assert task is not None
        attachment = AgentTaskAttachment(
            task_id=task.task_id,
            factory_id=task.factory_id,
            uploaded_by=runtime.user_id,
            tenant_id=old_binding.tenant_id,
            origin_generation=old_binding.generation,
            storage_namespace=f"tenant_{old_binding.tenant_id.hex}_{old_binding.generation}",
            storage_key=uuid.uuid4().hex,
            byte_size=5,
            sha256=hashlib.sha256(b"clean").hexdigest(),
            status="available",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(attachment)
        await db.commit()
        _write_clean_file(attachment)

    async with runtime.engine.begin() as platform:
        await platform.execute(text("UPDATE public.tenants SET generation=generation+1 WHERE id=:id"),
                               {"id": old_binding.tenant_id})
    new_binding = TenantBinding(old_binding.tenant_id, old_binding.schema_name, old_binding.generation + 1, "business")
    async with runtime.factory(binding=new_binding) as db:
        user = await db.get(__import__("app.models.user", fromlist=["User"]).User, runtime.user_id)
        assert user is not None
        scope = RequestScope(FactoryScope([], None), None, ProductLineScope("NONE", None), user)
        handle = await task_attachments.open_download(db, scope, runtime.task_id, attachment.attachment_id)
        try:
            assert handle.stream.read() == b"clean"
        finally:
            handle.stream.close()


@pytest.mark.asyncio
async def test_expired_known_historical_generation_is_purged_without_orphan_sweep(
    committed_runtime, attachment_settings,
):
    """Current tenant authority may purge its own expired old-generation row only."""
    runtime = committed_runtime
    recovery = recovery_module()
    old_generation = runtime.binding.generation - 1
    old_namespace = f"tenant_{runtime.binding.tenant_id.hex}_{old_generation}"
    async with runtime.factory(binding=runtime.binding) as db:
        task = await db.get(AgentTask, runtime.task_id)
        assert task is not None
        attachment = AgentTaskAttachment(
            task_id=task.task_id,
            factory_id=task.factory_id,
            uploaded_by=runtime.user_id,
            tenant_id=runtime.binding.tenant_id,
            origin_generation=old_generation,
            storage_namespace=old_namespace,
            storage_key=uuid.uuid4().hex,
            byte_size=5,
            sha256=hashlib.sha256(b"clean").hexdigest(),
            status="available",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(attachment)
        await db.commit()
        storage = _write_clean_file(attachment)
        namespace = _namespace(attachment)
        stats = await recovery.reconcile_live_namespace(db, namespace, storage, now=datetime.now(UTC))
        await db.refresh(attachment)

    assert stats.purged == 1
    assert attachment.status == "purged"

@pytest.mark.asyncio
async def test_expired_available_is_hidden_then_purged_with_system_audit(
    owned_attachment, attachment_settings,
):
    """Expiry hides bytes before cleanup; recovery owns the auditable final purge."""
    from sqlalchemy import select

    from app.models.audit import AuditLog
    from app.services.agent_runtime import task_attachments

    recovery = recovery_module()
    attachment = owned_attachment.attachment
    attachment.status = "available"
    attachment.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    storage = _write_clean_file(attachment)
    await owned_attachment.db.commit()

    assert await task_attachments.list_for_view(
        owned_attachment.db, owned_attachment.scope, owned_attachment.task.task_id
    ) == []

    stats = await recovery.reconcile_live_namespace(
        owned_attachment.db, _namespace(attachment), storage, now=datetime.now(UTC),
    )
    await owned_attachment.db.refresh(attachment)
    audit = await owned_attachment.db.scalar(
        select(AuditLog).where(
            AuditLog.record_id == attachment.attachment_id,
            AuditLog.action == "AGENT_TASK_ATTACHMENT_EXPIRED",
        )
    )

    assert stats.purged == 1
    assert attachment.status == "purged"
    assert attachment.deleted_at is not None
    assert audit is not None and audit.operated_by is None
    assert audit.changed_fields == {"status": "purged", "actor": "system", "reason": "expired"}
    with pytest.raises(FileNotFoundError):
        storage.open_clean(_namespace(attachment), attachment.attachment_id, attachment.sha256, attachment.byte_size)


@pytest.mark.asyncio
async def test_expiry_delete_failure_retries_with_exactly_one_system_audit(
    owned_attachment, attachment_settings, monkeypatch,
):
    """A crash/failure after durable purging never loses or duplicates expiry audit."""
    from sqlalchemy import func, select

    from app.models.audit import AuditLog

    recovery = recovery_module()
    attachment = owned_attachment.attachment
    attachment.status = "available"
    attachment.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    storage = _write_clean_file(attachment)
    await owned_attachment.db.commit()
    original_remove = storage.remove
    calls = 0

    def fail_once(namespace, attachment_id, area):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected delete failure")
        return original_remove(namespace, attachment_id, area)

    monkeypatch.setattr(storage, "remove", fail_once)
    with pytest.raises(OSError):
        await recovery.reconcile_live_namespace(
            owned_attachment.db, _namespace(attachment), storage, now=datetime.now(UTC),
        )
    await owned_attachment.db.refresh(attachment)
    assert attachment.status == "purging"

    monkeypatch.setattr(storage, "remove", original_remove)
    stats = await recovery.reconcile_live_namespace(
        owned_attachment.db, _namespace(attachment), storage, now=datetime.now(UTC),
    )
    audit_count = await owned_attachment.db.scalar(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.record_id == attachment.attachment_id,
            AuditLog.action == "AGENT_TASK_ATTACHMENT_EXPIRED",
        )
    )
    await owned_attachment.db.refresh(attachment)

    assert stats.purged == 1
    assert attachment.status == "purged"
    assert audit_count == 1


@pytest.mark.asyncio
async def test_attachment_startup_gates_runtime_and_real_scanner_handshake(monkeypatch, tmp_path):
    """Startup never opens storage/DB/scanner unless both flags and health are true."""
    import asyncio

    from app import main
    from app.services.agent_runtime import attachment_recovery

    root = tmp_path / "private"
    calls = 0

    async def reconciliation():
        nonlocal calls
        calls += 1
        return None

    monkeypatch.setattr(attachment_recovery, "reconcile_configured_storage", reconciliation)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", False)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_STORAGE_ROOT", str(root))
    assert await main.initialize_attachment_runtime(main.app) is False
    assert calls == 0 and not root.exists()

    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_CLAMAV_HOST", "")
    assert await main.initialize_attachment_runtime(main.app) is False
    assert settings.AGENT_TASK_ATTACHMENTS_ENABLED is False and calls == 0

    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)

    async def healthy(reader, writer):
        assert await reader.readuntil(b"\n") == b"nVERSIONCOMMANDS\n"
        writer.write(b"ClamAV 1.4.3/28150\nCOMMANDS: VERSIONCOMMANDS INSTREAM\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(healthy, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    try:
        monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_CLAMAV_HOST", host)
        monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_CLAMAV_PORT", port)
        assert await main.initialize_attachment_runtime(main.app) is True
        assert calls == 1 and main.app.state.agent_task_attachments_ready is True
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_attachment_startup_disables_after_malformed_real_health_reply(monkeypatch, tmp_path):
    import asyncio

    from app import main
    from app.services.agent_runtime import attachment_recovery

    async def must_not_reconcile():
        raise AssertionError("scanner health failure must precede database reconciliation")

    async def malformed(reader, writer):
        assert await reader.readuntil(b"\n") == b"nVERSIONCOMMANDS\n"
        writer.write(b"not-clamav\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(malformed, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    try:
        monkeypatch.setattr(attachment_recovery, "reconcile_configured_storage", must_not_reconcile)
        monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
        monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)
        monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_STORAGE_ROOT", str(tmp_path / "private"))
        monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_CLAMAV_HOST", host)
        monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_CLAMAV_PORT", port)
        assert await main.initialize_attachment_runtime(main.app) is False
        assert settings.AGENT_TASK_ATTACHMENTS_ENABLED is False
    finally:
        server.close()
        await server.wait_closed()
