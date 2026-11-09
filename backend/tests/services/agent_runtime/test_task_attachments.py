"""Database-backed lifecycle tests for controlled private task attachments.

Each test names the state or authority regression it must catch.  Filesystem
storage stays real except where an external scanner/physical-delete boundary is
observed through a minimal spy.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.config import settings
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.models.agent_task import AgentTask
from app.models.agent_task_attachment import AgentTaskAttachment
from app.models.audit import AuditLog
from app.models.role import RolePermission
from app.models.user import User


async def chunks(values: list[bytes]) -> AsyncIterator[bytes]:
    for value in values:
        yield value


def attachment_service():
    name = "app.services.agent_runtime.task_attachments"
    assert importlib.util.find_spec(name) is not None, "attachment lifecycle service is missing"
    return __import__(name, fromlist=["reserve_upload"])


@pytest_asyncio.fixture
async def owned_task(db, request_scope_all, sample_capa, enabled_plugin):
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
    return SimpleNamespace(
        db=db,
        scope=scope,
        task=task,
        task_id=task.task_id,
        factory_id=sample_capa.factory_id,
        plugin_id=enabled_plugin.installation_id,
        target_capa_id=sample_capa.report_id,
    )


@pytest.fixture
def attachment_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENTS_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_STORAGE_ROOT", str(tmp_path / "attachments"))
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_MAX_BYTES", 20 * 1024 * 1024)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_MAX_PER_TASK", 5)
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_RETENTION_HOURS", 168)
    return tmp_path


async def seed_attachment(owned, *, status: str, expires_at: datetime | None = None):
    attachment = AgentTaskAttachment(
        task_id=owned.task_id,
        factory_id=owned.factory_id,
        uploaded_by=owned.scope.user.user_id,
        tenant_id=None,
        origin_generation=None,
        storage_namespace="public",
        storage_key=uuid.uuid4().hex,
        display_name="safe.txt",
        extension="txt",
        declared_content_type="text/plain",
        byte_size=5,
        sha256=hashlib.sha256(b"clean").hexdigest(),
        status=status,
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
    )
    owned.db.add(attachment)
    await owned.db.flush()
    return attachment


@pytest.mark.asyncio
async def test_reservation_honors_configured_active_attachment_limit(owned_task, attachment_settings, monkeypatch):
    """Regression: configured quota, not a literal five, controls admission."""
    service = attachment_service()
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_MAX_PER_TASK", 1)
    await seed_attachment(owned_task, status="available")
    reservation = None
    try:
        with pytest.raises(service.AttachmentCapacityError):
            reservation = await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)
    finally:
        if reservation is not None:
            await service.abandon_upload(reservation)


@pytest.mark.asyncio
async def test_sixth_active_reservation_is_rejected(owned_task, attachment_settings):
    """Regression: sixth scanning/promoting/available slot must never be allocated."""
    service = attachment_service()
    for status in ["scanning", "promoting", "available", "available", "available"]:
        await seed_attachment(owned_task, status=status)

    with pytest.raises(service.AttachmentCapacityError):
        await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)


@pytest.mark.asyncio
async def test_reservation_is_scanning_for_exactly_180_seconds(owned_task, attachment_settings):
    """Regression: incomplete reservations must be quota-consuming but short lived."""
    service = attachment_service()
    before = datetime.now(UTC)
    reservation = await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)
    after = datetime.now(UTC)

    attachment = await owned_task.db.get(AgentTaskAttachment, reservation.attachment_id)
    assert attachment.status == "scanning"
    assert attachment.reservation_expires_at is not None
    assert before + timedelta(seconds=179) <= attachment.reservation_expires_at <= after + timedelta(seconds=181)
    await service.abandon_upload(reservation)
    assert (await owned_task.db.get(AgentTaskAttachment, reservation.attachment_id)).status == "failed_storage"


@pytest.mark.asyncio
async def test_reservation_uses_one_global_pipeline_slot_and_abandon_releases_it(
    owned_task, attachment_settings,
):
    """Regression: a reservation on any task blocks every other pipeline until request cleanup."""
    service = attachment_service()
    first = await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)
    other = AgentTask(
        initiator_id=owned_task.scope.user.user_id,
        executor_user_id=owned_task.scope.user.user_id,
        preferred_installation_id=owned_task.plugin_id,
        target_capa_id=owned_task.target_capa_id,
        factory_id=owned_task.factory_id,
        request_key=uuid.uuid4().hex,
        status="ready",
    )
    owned_task.db.add(other)
    await owned_task.db.commit()
    with pytest.raises(service.AttachmentCapacityError):
        await service.reserve_upload(owned_task.db, owned_task.scope, other.task_id)

    await service.abandon_upload(first)
    second = await service.reserve_upload(owned_task.db, owned_task.scope, other.task_id)
    await service.abandon_upload(second)


@pytest.mark.asyncio
async def test_expired_scanning_reservations_do_not_consume_capacity(owned_task, attachment_settings):
    """Regression: the 180-second reservation window must release admission capacity."""
    service = attachment_service()
    for _ in range(5):
        attachment = await seed_attachment(owned_task, status="scanning")
        attachment.reservation_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    reservation = await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)
    await service.abandon_upload(reservation)


@pytest.mark.asyncio
async def test_known_foreign_task_does_not_acquire_pipeline_slot_or_task_lock(
    owned_task, attachment_settings,
):
    """Regression: pre-admission rejects a known foreign UUID before global locking."""
    service = attachment_service()
    foreign = User(
        user_id=uuid.uuid4(),
        username="attachment-foreign-" + uuid.uuid4().hex[:8],
        password_hash="fixture",
        role_id=owned_task.scope.user.role_id,
        legacy_role="admin",
        is_active=True,
        factory_id=owned_task.factory_id,
    )
    owned_task.db.add(foreign)
    await owned_task.db.flush()
    owned_task.task.executor_user_id = foreign.user_id
    await owned_task.db.flush()

    with pytest.raises(LookupError):
        await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)

    owned_task.task.executor_user_id = owned_task.scope.user.user_id
    await owned_task.db.flush()
    reservation = await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)
    await service.abandon_upload(reservation)

@pytest.mark.asyncio
@pytest.mark.parametrize("task_status", ["completed", "blocked_capability", "cancelled"])
async def test_reservation_rejects_task_outside_ready_or_paused(owned_task, attachment_settings, task_status):
    """Regression: terminal or blocked tasks cannot create a private upload slot."""
    service = attachment_service()
    owned_task.task.status = task_status
    await owned_task.db.flush()

    with pytest.raises(service.AttachmentTaskStateError):
        await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)


@pytest.mark.asyncio
async def test_revocation_before_promotion_leaves_no_downloadable_blob(
    owned_task, attachment_settings, monkeypatch,
):
    """Regression: access revoked during scanning must prevent clean-blob promotion."""
    service = attachment_service()
    reservation = await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)

    async def clean_scan(reader, **_kwargs):
        async for _ in reader:
            pass
        return service.clamav_scan.ScanResult("clean", "ClamAV 1.4.2/12345", None)

    monkeypatch.setattr(service.clamav_scan, "scan_stream", clean_scan)
    await owned_task.db.execute(
        update(RolePermission)
        .where(RolePermission.role_id == owned_task.scope.user.role_id, RolePermission.module == "capa")
        .values(permission_level=0)
    )

    with pytest.raises(service.AttachmentSourceChanged):
        await service.receive_and_scan(reservation, chunks([b"clean"]))

    attachment = await owned_task.db.get(AgentTaskAttachment, reservation.attachment_id)
    assert attachment.status != "available"
    with pytest.raises(PermissionError):
        await service.open_download(
            owned_task.db, owned_task.scope, owned_task.task_id, reservation.attachment_id
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["cancel", "revoke"])
async def test_two_session_stale_authority_race_never_publishes_available(
    committed_runtime, attachment_settings, monkeypatch, change,
):
    """A pre-change read cannot survive a second session's committed change."""
    owned = committed_runtime
    service = attachment_service()
    ready_for_change = asyncio.Event()
    change_committed = asyncio.Event()

    async def clean_scan(reader, **_kwargs):
        async for _ in reader:
            pass
        ready_for_change.set()
        await change_committed.wait()
        return service.clamav_scan.ScanResult("clean", "ClamAV 1.4.2/12345", None)

    monkeypatch.setattr(service.clamav_scan, "scan_stream", clean_scan)
    async with owned.factory(binding=owned.binding) as upload:
        user = await upload.get(User, owned.user_id)
        assert user is not None
        scope = RequestScope(FactoryScope([], None), None, ProductLineScope("NONE", None), user)
        # Establish the stale pre-change authority read in the upload session.
        assert (await service.task_service.get_task_for_view(upload, scope, owned.task_id)).status == "ready"
        reservation = await service.reserve_upload(upload, scope, owned.task_id)
        receive = asyncio.create_task(service.receive_and_scan(reservation, chunks([b"clean"])))
        await ready_for_change.wait()
        async with owned.factory(binding=owned.binding) as rival:
            if change == "cancel":
                task = await rival.scalar(select(AgentTask).where(AgentTask.task_id == owned.task_id).with_for_update())
                assert task is not None
                task.status = "cancelled"
            else:
                await rival.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
                    RolePermission.module == "capa").values(permission_level=0))
            await rival.commit()
        change_committed.set()
        with pytest.raises(service.AttachmentSourceChanged):
            await receive
        attachment = await upload.get(AgentTaskAttachment, reservation.attachment_id)
        assert attachment is not None and attachment.status == "failed_storage"
        assert not (await upload.scalars(select(AuditLog.action).where(
            AuditLog.record_id == reservation.attachment_id,
            AuditLog.action == "AGENT_TASK_ATTACHMENT_RESULT",
            AuditLog.changed_fields["status"].astext == "available",
        ))).all()


@pytest.mark.asyncio
async def test_stream_limit_has_distinct_safe_exception_for_http_413(
    owned_task, attachment_settings, monkeypatch,
):
    """Regression: bounded input rejection must remain distinguishable from storage failure."""
    service = attachment_service()
    monkeypatch.setattr(settings, "AGENT_TASK_ATTACHMENT_MAX_BYTES", 4)
    reservation = await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)

    async def consume_scan(reader, **_kwargs):
        async for _ in reader:
            pass
        return service.clamav_scan.ScanResult("clean", "ClamAV 1.4.2/12345", None)

    monkeypatch.setattr(service.clamav_scan, "scan_stream", consume_scan)
    with pytest.raises(service.AttachmentInputLimitError):
        await service.receive_and_scan(reservation, chunks([b"clean"]))
    attachment = await owned_task.db.get(AgentTaskAttachment, reservation.attachment_id)
    assert (attachment.status, attachment.failure_code) == ("failed_storage", "input_limit")


@pytest.mark.asyncio
async def test_clean_scan_promotes_descriptor_backed_no_store_download(
    owned_task, attachment_settings, monkeypatch,
):
    """Regression: clean bytes become one reverified, non-cacheable attachment download."""
    service = attachment_service()
    reservation = await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)

    async def clean_scan(reader, **_kwargs):
        async for _ in reader:
            pass
        return service.clamav_scan.ScanResult("clean", "ClamAV 1.4.2/12345", None)

    monkeypatch.setattr(service.clamav_scan, "scan_stream", clean_scan)
    attachment = await service.receive_and_scan(reservation, chunks([b"clean"]))

    assert (attachment.status, attachment.byte_size, attachment.display_name) == ("available", 5, None)
    assert await service.list_for_view(owned_task.db, owned_task.scope, owned_task.task_id) == [attachment]
    handle = await service.open_download(
        owned_task.db, owned_task.scope, owned_task.task_id, attachment.attachment_id
    )
    try:
        assert handle.stream.read() == b"clean"
    finally:
        handle.stream.close()
    assert handle.headers["Content-Type"] == "application/octet-stream"
    assert handle.headers["X-Content-Type-Options"] == "nosniff"
    assert handle.headers["Cache-Control"] == "no-store"
    assert handle.headers["Content-Disposition"].startswith("attachment; filename=\"attachment-")


@pytest.mark.asyncio
async def test_only_available_unexpired_attachment_can_open_download(owned_task, attachment_settings):
    """Regression: rejected or expired metadata must not open a private descriptor."""
    service = attachment_service()
    rejected = await seed_attachment(owned_task, status="rejected_malware")
    expired = await seed_attachment(
        owned_task, status="available", expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )

    for attachment in [rejected, expired]:
        with pytest.raises(LookupError):
            await service.open_download(
                owned_task.db, owned_task.scope, owned_task.task_id, attachment.attachment_id
            )


async def prepare_clean_download(owned, service):
    attachment = await seed_attachment(owned, status="available")
    binding = owned.db.info.get("tenant_binding")
    if binding is not None:
        attachment.tenant_id = binding.tenant_id
        attachment.origin_generation = binding.generation
        attachment.storage_namespace = f"tenant_{binding.tenant_id.hex}_{binding.generation}"
    storage = service._storage()
    namespace = service._namespace(attachment)
    with storage.create_staging(namespace, attachment.attachment_id) as stream:
        stream.write(b"clean")
    storage.promote(namespace, attachment.attachment_id, attachment.sha256, attachment.byte_size)
    await owned.db.commit()
    return attachment


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    "revoke", "disable", "retarget", "purging", "expire", "digest",
    "namespace", "origin_generation", "tenant", "unchanged",
])
async def test_download_rechecks_committed_changes_after_file_verification(
    committed_runtime, attachment_settings, monkeypatch, change,
):
    """A real second transaction changes authority after the descriptor is verified."""
    from app.models.capa import CAPAEightD

    owned = committed_runtime
    service = attachment_service()
    verified = asyncio.Event()
    changed = asyncio.Event()
    streams = []
    original_open = service.attachment_storage.PrivateAttachmentStorage.open_clean

    def observe_open(storage, *args):
        stream = original_open(storage, *args)
        streams.append(stream)
        verified.set()
        return stream

    async with owned.factory(binding=owned.binding) as download:
        user = await download.get(User, owned.user_id)
        task = await download.get(AgentTask, owned.task_id)
        scope = RequestScope(FactoryScope([], None), None, ProductLineScope("NONE", None), user)
        attachment = await prepare_clean_download(SimpleNamespace(
            db=download, task_id=owned.task_id, factory_id=task.factory_id, scope=scope,
        ), service)
        attachment_id = attachment.attachment_id
        original_execute = download.execute
        original_commit = download.commit

        async def fence_execute(*args, **kwargs):
            if verified.is_set():
                await changed.wait()
            return await original_execute(*args, **kwargs)

        async def fence_commit():
            if verified.is_set():
                await changed.wait()
            await original_commit()

        async def rival_change():
            await verified.wait()
            try:
                async with owned.factory(binding=owned.binding) as rival:
                    if change == "revoke":
                        await rival.execute(update(RolePermission).where(
                            RolePermission.role_id == owned.role_id, RolePermission.module == "capa",
                        ).values(permission_level=0))
                    elif change == "disable":
                        await rival.execute(update(User).where(User.user_id == owned.user_id).values(is_active=False))
                    elif change == "retarget":
                        target = await rival.get(CAPAEightD, task.target_capa_id)
                        replacement = CAPAEightD(document_no="8D-RETARGET", title="Replacement",
                            factory_id=target.factory_id, product_line_code=target.product_line_code,
                            created_by=owned.user_id)
                        rival.add(replacement)
                        await rival.flush()
                        await rival.execute(update(AgentTask).where(AgentTask.task_id == owned.task_id)
                            .values(target_capa_id=replacement.report_id))
                    elif change in {"purging", "expire", "digest", "namespace", "origin_generation", "tenant"}:
                        values = {"purging": {"status": "purging"},
                            "expire": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
                            "digest": {"sha256": "0" * 64},
                            "namespace": {"storage_namespace": f"tenant_{owned.binding.tenant_id.hex}_{owned.binding.generation + 1}"},
                            "origin_generation": {"origin_generation": owned.binding.generation + 1},
                            "tenant": {"tenant_id": uuid.uuid4()}}[change]
                        await rival.execute(update(AgentTaskAttachment).where(
                            AgentTaskAttachment.attachment_id == attachment_id).values(**values))
                    await rival.commit()
            finally:
                changed.set()

        monkeypatch.setattr(service.attachment_storage.PrivateAttachmentStorage, "open_clean", observe_open)
        monkeypatch.setattr(download, "execute", fence_execute)
        monkeypatch.setattr(download, "commit", fence_commit)
        rival = asyncio.create_task(rival_change())
        try:
            async with asyncio.timeout(20):
                if change == "unchanged":
                    handle = await service.open_download(download, scope, owned.task_id, attachment_id)
                    assert handle.stream.read() == b"clean"
                    handle.stream.close()
                else:
                    with pytest.raises((PermissionError, LookupError)):
                        await service.open_download(download, scope, owned.task_id, attachment_id)
                    assert streams and streams[0].closed
                await rival
            # Even if the caller later commits, a denied download must leave no success audit.
            await original_commit()
            actions = (await download.scalars(select(AuditLog.action).where(
                AuditLog.record_id == attachment_id,
                AuditLog.action == "AGENT_TASK_ATTACHMENT_DOWNLOAD",
            ))).all()
            assert actions == (["AGENT_TASK_ATTACHMENT_DOWNLOAD"] if change == "unchanged" else [])
        finally:
            rival.cancel()
            await asyncio.gather(rival, return_exceptions=True)
            for stream in streams:
                stream.close()


@pytest.mark.asyncio
async def test_download_expiring_during_file_verification_closes_descriptor(
    owned_task, attachment_settings, monkeypatch,
):
    service = attachment_service()
    attachment = await prepare_clean_download(owned_task, service)
    expires_at = attachment.expires_at
    streams = []
    original_open = service.attachment_storage.PrivateAttachmentStorage.open_clean

    def expire_after_verification(storage, *args):
        stream = original_open(storage, *args)
        streams.append(stream)
        monkeypatch.setattr(service, "_now", lambda: expires_at)
        return stream

    monkeypatch.setattr(service.attachment_storage.PrivateAttachmentStorage, "open_clean", expire_after_verification)
    try:
        with pytest.raises(LookupError):
            await service.open_download(owned_task.db, owned_task.scope, owned_task.task_id, attachment.attachment_id)
        assert streams and streams[0].closed
        assert not (await owned_task.db.scalars(select(AuditLog).where(
            AuditLog.record_id == attachment.attachment_id, AuditLog.action == "AGENT_TASK_ATTACHMENT_DOWNLOAD",
        ))).all()
    finally:
        for stream in streams:
            stream.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_download_commit_failure_closes_verified_descriptor_without_success_audit(
    owned_task, attachment_settings, monkeypatch, failure,
):
    service = attachment_service()
    attachment = await prepare_clean_download(owned_task, service)
    attachment_id = attachment.attachment_id
    streams = []
    original_open = service.attachment_storage.PrivateAttachmentStorage.open_clean
    original_commit = owned_task.db.commit

    def observe_open(storage, *args):
        stream = original_open(storage, *args)
        streams.append(stream)
        return stream

    async def fail_commit():
        raise failure("download commit interrupted")

    monkeypatch.setattr(service.attachment_storage.PrivateAttachmentStorage, "open_clean", observe_open)
    monkeypatch.setattr(owned_task.db, "commit", fail_commit)
    try:
        with pytest.raises(failure):
            await service.open_download(owned_task.db, owned_task.scope, owned_task.task_id, attachment_id)
        assert streams and streams[0].closed
        await original_commit()
        assert not (await owned_task.db.scalars(select(AuditLog).where(
            AuditLog.record_id == attachment_id, AuditLog.action == "AGENT_TASK_ATTACHMENT_DOWNLOAD",
        ))).all()
    finally:
        for stream in streams:
            stream.close()


@pytest.mark.asyncio
async def test_delete_commits_purging_before_physical_delete(
    owned_task, attachment_settings, monkeypatch,
):
    """Regression: a failed physical delete must leave durable purging evidence, not resurrect access."""
    service = attachment_service()
    attachment = await seed_attachment(owned_task, status="available")
    observed_statuses: list[str] = []
    commits: list[str] = []
    original_commit = owned_task.db.commit

    async def observe_commit():
        await original_commit()
        commits.append("commit")

    monkeypatch.setattr(owned_task.db, "commit", observe_commit)

    class StorageSpy:
        def __init__(self, _root: Path):
            pass

        def remove(self, _namespace, attachment_id, area):
            assert area == "clean"
            assert attachment_id == attachment.attachment_id
            assert commits == ["commit"]
            observed_statuses.append("purging")

    monkeypatch.setattr(service.attachment_storage, "PrivateAttachmentStorage", StorageSpy)
    await service.purge_for_owner(
        owned_task.db, owned_task.scope, owned_task.task_id, attachment.attachment_id
    )

    assert observed_statuses == ["purging"]
    assert commits == ["commit", "commit"]
    assert (await owned_task.db.get(AgentTaskAttachment, attachment.attachment_id)).status == "purged"
    audit_actions = (await owned_task.db.scalars(
        select(AuditLog.action).where(AuditLog.record_id == attachment.attachment_id)
    )).all()
    assert audit_actions == ["AGENT_TASK_ATTACHMENT_DELETE"]


@pytest.mark.asyncio
async def test_attachment_audits_never_contain_filename_content_storage_or_daemon_output(
    owned_task, attachment_settings,
):
    """Regression: attachment audit payloads must remain safe operational metadata only."""
    service = attachment_service()
    reservation = await service.reserve_upload(owned_task.db, owned_task.scope, owned_task.task_id)
    rows = (await owned_task.db.scalars(
        select(AuditLog).where(AuditLog.record_id == reservation.attachment_id)
    )).all()

    assert [row.action for row in rows] == ["AGENT_TASK_ATTACHMENT_RESERVED"]
    serialized = " ".join(str(row.changed_fields) for row in rows).lower()
    for forbidden in ["filename", "clean", "storage_key", "path", "clamav"]:
        assert forbidden not in serialized
    await service.abandon_upload(reservation)
