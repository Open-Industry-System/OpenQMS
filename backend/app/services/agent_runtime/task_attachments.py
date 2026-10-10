"""Authorized, scan-gated lifecycle for private agent task attachments.

This service deliberately has no HTTP or multipart knowledge.  A caller reserves
one bounded slot, streams it through the scanner, and receives only safe
metadata or a descriptor-backed download handle.
"""
from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Final
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.config import settings
from app.core.deps import RequestScope
from app.core.tenant_transaction import TenantBinding
from app.models.agent_task import AgentTask
from app.models.agent_task_attachment import AgentTaskAttachment
from app.models.audit import AuditLog
from app.services.agent_runtime import attachment_storage, clamav_scan, task_service


_ACTIVE_STATUSES: Final = ("scanning", "promoting", "available")
_RESERVATION_SECONDS: Final = 180
_LOCK_NAMESPACE: Final = 0x415454414348  # "ATTACH" domain separation.
_PREHELD_LOCK_SQL: Final = """
    SELECT EXISTS (SELECT 1 FROM pg_locks
    WHERE locktype='advisory' AND granted AND pid=pg_backend_pid() AND objsubid=1
      AND database=(SELECT oid FROM pg_database WHERE datname=current_database())
      AND classid=((CAST(:key AS bigint) >> 32) & 4294967295)::oid
      AND objid=(CAST(:key AS bigint) & 4294967295)::oid)
"""


class AttachmentCapacityError(ValueError):
    """The task already owns all five active attachment slots."""


class AttachmentTaskStateError(ValueError):
    """The task is not accepting attachment reservations."""


class AttachmentSourceChanged(PermissionError):
    """Current user/tenant/task authority changed before clean promotion."""


class AttachmentInputLimitError(ValueError):
    """The bounded input stream exceeded the fixed attachment limit."""


class _ReservationExpired(ValueError):
    pass


@dataclass(frozen=True)
class AttachmentView:
    attachment_id: UUID
    display_name: str | None
    byte_size: int | None
    status: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


@dataclass
class ReservedAttachment:
    attachment_id: UUID
    task_id: UUID
    db: AsyncSession
    scope: RequestScope
    binding: TenantBinding | None
    lock_connection: AsyncConnection
    slot_released: bool = False

    async def __aenter__(self) -> ReservedAttachment:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if not self.slot_released:
            await abandon_upload(self)


@dataclass(frozen=True)
class DownloadHandle:
    stream: BinaryIO
    headers: dict[str, str]


def _now() -> datetime:
    return datetime.now(UTC)


def _namespace(attachment: AgentTaskAttachment) -> attachment_storage.AttachmentNamespace:
    return attachment_storage.AttachmentNamespace(
        tenant_id=attachment.tenant_id,
        origin_generation=attachment.origin_generation,
        storage_namespace=attachment.storage_namespace,
    )


def _storage() -> attachment_storage.PrivateAttachmentStorage:
    if not settings.AGENT_TASK_ATTACHMENT_STORAGE_ROOT:
        raise RuntimeError("attachment storage is unavailable")
    return attachment_storage.PrivateAttachmentStorage(Path(settings.AGENT_TASK_ATTACHMENT_STORAGE_ROOT))


def _lock_key() -> int:
    """One process-independent scanner/upload pipeline slot for every task."""
    return int.from_bytes(
        hashlib.sha256(_LOCK_NAMESPACE.to_bytes(8, "big")).digest()[:8],
        "big",
        signed=True,
    )


async def _acquire_slot_lock(db: AsyncSession) -> AsyncConnection:
    bind = db.bind
    if bind is None or not hasattr(bind, "connect"):
        raise RuntimeError("attachment reservation requires an engine-bound session")
    connection = await bind.connect()
    try:
        # Session advisory locks are reentrant: pooled lock contamination must
        # be discarded instead of treated as a successful fresh acquisition.
        preheld = await connection.scalar(text(_PREHELD_LOCK_SQL), {"key": _lock_key()})
        if preheld:
            await connection.invalidate()
            raise RuntimeError("attachment pipeline connection was pre-locked")
        held = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": _lock_key()})
        if not held:
            raise AttachmentCapacityError("attachment pipeline is busy")
        await connection.commit()
        return connection
    except BaseException:
        # Any failure after an acquisition is uncertain: only invalidation
        # guarantees a session-level lock cannot return to the pool.
        await connection.invalidate()
        await connection.close()
        raise


async def _release_slot_lock(reservation: ReservedAttachment) -> None:
    if reservation.slot_released:
        return
    connection = reservation.lock_connection
    try:
        if connection.invalidated:
            return
        if connection.in_transaction():
            await connection.rollback()
        released = await connection.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": _lock_key()})
        if not released:
            raise RuntimeError("attachment pipeline lock release failed")
        await connection.rollback()
    except BaseException:
        await connection.invalidate()
        raise
    finally:
        reservation.slot_released = True
        await connection.close()


async def _locked_task(db: AsyncSession, scope: RequestScope, task_id: UUID) -> AgentTask:
    """Lock fresh task state, then authorize current user/CAPA authority after any wait."""
    task = await db.scalar(
        select(AgentTask)
        .where(AgentTask.task_id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if task is None:
        raise LookupError("Task not found")
    authorized = await task_service.get_task_for_view(db, scope, task_id)
    if authorized.task_id != task.task_id:
        raise LookupError("Task not found")
    return task


def _storage_namespace(binding: TenantBinding | None) -> tuple[UUID | None, int | None, str]:
    if binding is None:
        return None, None, "public"
    return binding.tenant_id, binding.generation, f"tenant_{binding.tenant_id.hex}_{binding.generation}"


def _view(attachment: AgentTaskAttachment) -> AttachmentView:
    return AttachmentView(
        attachment_id=attachment.attachment_id,
        display_name=attachment.display_name,
        byte_size=attachment.byte_size,
        status=attachment.status,
        created_at=attachment.created_at,
        updated_at=attachment.updated_at,
        expires_at=attachment.expires_at,
    )


def _audit(db: AsyncSession, attachment: AgentTaskAttachment, actor_id: UUID, action: str, *, status: str) -> None:
    """Record only lifecycle facts; never persist names, bytes, paths or scanner text."""
    db.add(AuditLog(
        table_name="agent_task_attachments",
        record_id=attachment.attachment_id,
        action=action,
        operated_by=actor_id,
        factory_id=attachment.factory_id,
        changed_fields={"status": status},
    ))


async def reserve_upload(db: AsyncSession, scope: RequestScope, task_id: UUID) -> ReservedAttachment:
    """Reserve one serialized task slot and commit before a caller reads bytes."""
    binding = db.info.get("tenant_binding")
    if binding is not None and not isinstance(binding, TenantBinding):
        raise AttachmentSourceChanged("attachment tenant binding changed")
    lock_connection = await _acquire_slot_lock(db)
    try:
        task = await _locked_task(db, scope, task_id)
        if task.status not in {"ready", "paused"}:
            raise AttachmentTaskStateError("task is not accepting attachments")
        now = _now()
        active_count = await db.scalar(
            select(func.count()).select_from(AgentTaskAttachment).where(
                AgentTaskAttachment.task_id == task.task_id,
                or_(
                    AgentTaskAttachment.status.in_(("promoting", "available")),
                    (AgentTaskAttachment.status == "scanning")
                    & or_(
                        AgentTaskAttachment.reservation_expires_at.is_(None),
                        AgentTaskAttachment.reservation_expires_at > now,
                    ),
                ),
            )
        )
        if active_count >= 5:
            raise AttachmentCapacityError("attachment capacity reached")
        tenant_id, generation, namespace = _storage_namespace(binding)
        attachment = AgentTaskAttachment(
            task_id=task.task_id,
            factory_id=task.factory_id,
            uploaded_by=scope.user.user_id,
            tenant_id=tenant_id,
            origin_generation=generation,
            storage_namespace=namespace,
            storage_key="pending",
            status="scanning",
            reservation_expires_at=now + timedelta(seconds=_RESERVATION_SECONDS),
            expires_at=now + timedelta(hours=settings.AGENT_TASK_ATTACHMENT_RETENTION_HOURS),
        )
        db.add(attachment)
        await db.flush()
        attachment.storage_key = attachment.attachment_id.hex
        _audit(db, attachment, scope.user.user_id, "AGENT_TASK_ATTACHMENT_RESERVED", status="scanning")
        await db.commit()
        return ReservedAttachment(
            attachment_id=attachment.attachment_id,
            task_id=task.task_id,
            db=db,
            scope=scope,
            binding=binding,
            lock_connection=lock_connection,
        )
    except BaseException:
        await db.rollback()
        await _release_slot_lock(ReservedAttachment(task_id=task_id, attachment_id=task_id, db=db,
            scope=scope, binding=binding, lock_connection=lock_connection))
        raise


async def _transition_failure(reservation: ReservedAttachment, *, status: str, failure_code: str) -> None:
    attachment = await reservation.db.get(AgentTaskAttachment, reservation.attachment_id)
    if attachment is None:
        return
    storage = _storage()
    for area in ("staging", "clean"):
        try:
            storage.remove(_namespace(attachment), attachment.attachment_id, area)
        except OSError:
            # Metadata must still become terminal and free the reservation quota.
            pass
    attachment.status = status
    attachment.failure_code = failure_code
    attachment.reservation_expires_at = None
    _audit(
        reservation.db,
        attachment,
        reservation.scope.user.user_id,
        "AGENT_TASK_ATTACHMENT_RESULT",
        status=status,
    )
    await reservation.db.commit()
    await reservation.db.refresh(attachment)


async def abandon_upload(reservation: ReservedAttachment) -> None:
    """Release an unconsumed reservation when request setup/body streaming exits."""
    if reservation.slot_released:
        return
    try:
        attachment = await reservation.db.get(AgentTaskAttachment, reservation.attachment_id)
        if attachment is not None and attachment.status in {"scanning", "promoting"}:
            await _transition_failure(reservation, status="failed_storage", failure_code="abandoned")
    finally:
        await _release_slot_lock(reservation)


async def receive_and_scan(reservation: ReservedAttachment, chunks: AsyncIterator[bytes]) -> AttachmentView:
    """Write once, scan once, and promote only after current authority rechecks."""
    db = reservation.db
    storage = _storage()
    file_handle = None
    size = 0
    digest = hashlib.sha256()
    try:
        attachment = await db.get(AgentTaskAttachment, reservation.attachment_id)
        if attachment is None or attachment.status != "scanning":
            raise LookupError("attachment reservation not found")
        file_handle = storage.create_staging(_namespace(attachment), attachment.attachment_id)

        async def staged_chunks() -> AsyncIterator[bytes]:
            nonlocal size
            async for chunk in chunks:
                if not isinstance(chunk, bytes):
                    raise AttachmentInputLimitError("attachment input must be bytes")
                size += len(chunk)
                if size > settings.AGENT_TASK_ATTACHMENT_MAX_BYTES:
                    raise AttachmentInputLimitError("attachment input limit exceeded")
                file_handle.write(chunk)
                digest.update(chunk)
                yield chunk

        remaining = (attachment.reservation_expires_at - _now()).total_seconds() if attachment.reservation_expires_at else 0
        if remaining <= 0:
            raise _ReservationExpired("attachment reservation expired")
        async with asyncio.timeout(remaining):
            scan = await clamav_scan.scan_stream(
                staged_chunks(),
                host=settings.AGENT_TASK_ATTACHMENT_CLAMAV_HOST,
                port=settings.AGENT_TASK_ATTACHMENT_CLAMAV_PORT,
                timeout_seconds=settings.AGENT_TASK_ATTACHMENT_SCAN_TIMEOUT_SECONDS,
            )
        file_handle.close()
        file_handle = None
        if scan.outcome == "found":
            await _transition_failure(reservation, status="rejected_malware", failure_code="malware_detected")
            attachment = await db.get(AgentTaskAttachment, reservation.attachment_id)
            assert attachment is not None
            return _view(attachment)
        if scan.outcome != "clean":
            await _transition_failure(reservation, status="rejected_scanner", failure_code="scanner_unavailable")
            attachment = await db.get(AgentTaskAttachment, reservation.attachment_id)
            assert attachment is not None
            return _view(attachment)

        # Re-read the current authority and captured binding immediately before
        # the irreversible staging-to-clean promotion.
        if db.info.get("tenant_binding") != reservation.binding:
            raise AttachmentSourceChanged("attachment tenant binding changed")
        try:
            task = await _locked_task(db, reservation.scope, reservation.task_id)
        except (LookupError, PermissionError) as exc:
            raise AttachmentSourceChanged("attachment source changed") from exc
        if task.status not in {"ready", "paused"}:
            raise AttachmentSourceChanged("task no longer accepts attachments")
        attachment = await db.get(AgentTaskAttachment, reservation.attachment_id)
        if attachment is None or attachment.task_id != task.task_id or attachment.status != "scanning":
            raise AttachmentSourceChanged("attachment source changed")
        attachment.byte_size = size
        attachment.sha256 = digest.hexdigest()
        attachment.scanner_version = scan.scanner_version
        attachment.scanned_at = _now()
        attachment.reservation_expires_at = None
        attachment.status = "promoting"
        await db.commit()

        storage.promote(_namespace(attachment), attachment.attachment_id, attachment.sha256, attachment.byte_size)
        # Promotion is a separate durable phase. Re-authorize again afterwards
        # while holding the task row before the only available publication.
        if db.info.get("tenant_binding") != reservation.binding:
            raise AttachmentSourceChanged("attachment tenant binding changed")
        try:
            task = await _locked_task(db, reservation.scope, reservation.task_id)
        except (LookupError, PermissionError) as exc:
            raise AttachmentSourceChanged("attachment source changed") from exc
        attachment = await db.get(AgentTaskAttachment, reservation.attachment_id)
        if (task.status not in {"ready", "paused"} or attachment is None
                or attachment.task_id != task.task_id or attachment.status != "promoting"):
            raise AttachmentSourceChanged("attachment source changed")
        attachment.status = "available"
        _audit(db, attachment, reservation.scope.user.user_id, "AGENT_TASK_ATTACHMENT_RESULT", status="available")
        await db.commit()
        await db.refresh(attachment)
        return _view(attachment)
    except AttachmentSourceChanged:
        if file_handle is not None:
            file_handle.close()
        await _transition_failure(reservation, status="failed_storage", failure_code="source_changed")
        raise
    except asyncio.CancelledError:
        if file_handle is not None:
            file_handle.close()
        await _transition_failure(reservation, status="failed_storage", failure_code="cancelled")
        raise
    except (_ReservationExpired, asyncio.TimeoutError):
        if file_handle is not None:
            file_handle.close()
        await _transition_failure(reservation, status="failed_storage", failure_code="reservation_expired")
        attachment = await db.get(AgentTaskAttachment, reservation.attachment_id)
        assert attachment is not None
        return _view(attachment)
    except AttachmentInputLimitError:
        if file_handle is not None:
            file_handle.close()
        await _transition_failure(reservation, status="failed_storage", failure_code="input_limit")
        raise
    except (OSError, ValueError, AttachmentStorageError):
        if file_handle is not None:
            file_handle.close()
        await _transition_failure(reservation, status="failed_storage", failure_code="storage_failed")
        attachment = await db.get(AgentTaskAttachment, reservation.attachment_id)
        assert attachment is not None
        return _view(attachment)
    finally:
        await _release_slot_lock(reservation)


# Aliasing the primitive error keeps the narrow exception clause readable while
# preserving the storage module as the only implementation of descriptor safety.
AttachmentStorageError = attachment_storage.AttachmentIntegrityError


async def list_for_view(db: AsyncSession, scope: RequestScope, task_id: UUID) -> list[AttachmentView]:
    task = await task_service.get_task_for_view(db, scope, task_id)
    rows = (await db.scalars(
        select(AgentTaskAttachment)
        .where(AgentTaskAttachment.task_id == task.task_id)
        .order_by(AgentTaskAttachment.created_at, AgentTaskAttachment.attachment_id)
    )).all()
    return [_view(row) for row in rows]


async def open_download(
    db: AsyncSession, scope: RequestScope, task_id: UUID, attachment_id: UUID
) -> DownloadHandle:
    task = await task_service.get_task_for_view(db, scope, task_id)
    attachment = await db.scalar(
        select(AgentTaskAttachment).where(
            AgentTaskAttachment.task_id == task.task_id,
            AgentTaskAttachment.attachment_id == attachment_id,
            AgentTaskAttachment.status == "available",
        )
    )
    if attachment is None or attachment.expires_at <= _now() or attachment.sha256 is None or attachment.byte_size is None:
        raise LookupError("attachment not found")
    try:
        stream = _storage().open_clean(
            _namespace(attachment), attachment.attachment_id, attachment.sha256, attachment.byte_size
        )
    except (OSError, ValueError, attachment_storage.AttachmentIntegrityError) as exc:
        raise LookupError("attachment not found") from exc
    _audit(db, attachment, scope.user.user_id, "AGENT_TASK_ATTACHMENT_DOWNLOAD", status="available")
    await db.commit()
    return DownloadHandle(
        stream=stream,
        headers={
            "Content-Disposition": f'attachment; filename="attachment-{attachment.attachment_id}.bin"',
            "Content-Type": "application/octet-stream",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


async def purge_for_owner(
    db: AsyncSession, scope: RequestScope, task_id: UUID, attachment_id: UUID
) -> None:
    task = await _locked_task(db, scope, task_id)
    attachment = await db.scalar(
        select(AgentTaskAttachment)
        .where(
            AgentTaskAttachment.task_id == task.task_id,
            AgentTaskAttachment.attachment_id == attachment_id,
        )
        .with_for_update()
    )
    if attachment is None or attachment.status != "available":
        raise LookupError("attachment not found")
    attachment.status = "purging"
    await db.commit()
    try:
        _storage().remove(_namespace(attachment), attachment.attachment_id, "clean")
    except OSError:
        await db.rollback()
        raise
    attachment.status = "purged"
    attachment.deleted_at = _now()
    _audit(db, attachment, scope.user.user_id, "AGENT_TASK_ATTACHMENT_DELETE", status="purged")
    await db.commit()
