"""Platform-authorized recovery for private task attachment storage.

Recovery uses durable lifecycle metadata and platform disposal records only.  It
never evaluates an upload owner's current permissions and never manufactures an
available row for bytes that have no matching durable attachment record.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.tenant_transaction import TenantBinding
from app.models.agent_task_attachment import AgentTaskAttachment
from app.models.audit import AuditLog
from app.models.tenant_attachment_disposal import TenantAttachmentStorageDisposal
from app.services.agent_runtime.attachment_storage import AttachmentNamespace, PrivateAttachmentStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconcileStats:
    promoted: int = 0
    failed_scanning: int = 0
    failed_promoting: int = 0
    purged: int = 0
    unreferenced_objects: int = 0
    disposed_namespaces: int = 0
    preserved_unknown_namespaces: int = 0

    def plus(self, other: "ReconcileStats") -> "ReconcileStats":
        return ReconcileStats(**{
            field: getattr(self, field) + getattr(other, field)
            for field in self.__dataclass_fields__
        })


def _namespace_for_disposal(disposal: TenantAttachmentStorageDisposal) -> AttachmentNamespace:
    expected = f"tenant_{disposal.tenant_id.hex}_{disposal.origin_generation}"
    if disposal.storage_namespace != expected:
        raise ValueError("disposal namespace is not the exact tenant generation namespace")
    return AttachmentNamespace(
        tenant_id=disposal.tenant_id,
        origin_generation=disposal.origin_generation,
        storage_namespace=disposal.storage_namespace,
    )


def _close_verified_clean(
    storage: PrivateAttachmentStorage,
    namespace: AttachmentNamespace,
    attachment: AgentTaskAttachment,
) -> bool:
    if attachment.sha256 is None or attachment.byte_size is None:
        return False
    try:
        handle = storage.open_clean(namespace, attachment.attachment_id, attachment.sha256, attachment.byte_size)
    except (OSError, ValueError):
        return False
    handle.close()
    return True


def _discard_inflight(storage: PrivateAttachmentStorage, namespace: AttachmentNamespace, attachment_id) -> None:
    for area in ("staging", "clean"):
        storage.remove(namespace, attachment_id, area)


def _require_live_namespace(db: AsyncSession, namespace: AttachmentNamespace) -> None:
    binding = db.info.get("tenant_binding")
    if namespace.tenant_id is None:
        if binding is not None or namespace.storage_namespace != "public":
            raise PermissionError("public attachment namespace requires a public session")
        return
    if not isinstance(binding, TenantBinding):
        raise PermissionError("tenant attachment recovery requires a bound tenant session")
    if (namespace.tenant_id != binding.tenant_id
            or namespace.storage_namespace != f"tenant_{binding.tenant_id.hex}_{namespace.origin_generation}"):
        raise PermissionError("attachment recovery namespace does not belong to bound tenant")


async def _ensure_expiry_audit(db: AsyncSession, attachment: AgentTaskAttachment) -> None:
    existing = await db.scalar(
        select(AuditLog.log_id).where(
            AuditLog.record_id == attachment.attachment_id,
            AuditLog.action == "AGENT_TASK_ATTACHMENT_EXPIRED",
        ).limit(1)
    )
    if existing is None:
        db.add(AuditLog(
            table_name="agent_task_attachments",
            record_id=attachment.attachment_id,
            action="AGENT_TASK_ATTACHMENT_EXPIRED",
            operated_by=None,
            factory_id=attachment.factory_id,
            changed_fields={"status": "purging", "actor": "system", "reason": "expired"},
        ))


async def _reconcile_live_namespace_unlocked(
    db: AsyncSession,
    namespace: AttachmentNamespace,
    storage: PrivateAttachmentStorage,
    *,
    now: datetime,
) -> ReconcileStats:
    """Complete only durable work for one queryable live attachment table."""
    _require_live_namespace(db, namespace)
    rows = (await db.scalars(
        select(AgentTaskAttachment).where(
            AgentTaskAttachment.tenant_id == namespace.tenant_id,
            AgentTaskAttachment.origin_generation == namespace.origin_generation,
            AgentTaskAttachment.storage_namespace == namespace.storage_namespace,
        )
    )).all()
    promoted = failed_scanning = failed_promoting = purged = 0
    referenced_ids = {row.attachment_id for row in rows}

    for attachment in rows:
        if attachment.status == "available" and attachment.expires_at <= now:
            # Persist both purge authority and its system audit before bytes move.
            # A later filesystem failure leaves a durable, retryable purging row.
            attachment.status = "purging"
            attachment.failure_code = "expired"
            await _ensure_expiry_audit(db, attachment)
            await db.commit()
            _discard_inflight(storage, namespace, attachment.attachment_id)
            attachment.status = "purged"
            attachment.deleted_at = now
            await db.commit()
            purged += 1
        elif attachment.status == "scanning":
            if attachment.reservation_expires_at is not None and attachment.reservation_expires_at <= now:
                _discard_inflight(storage, namespace, attachment.attachment_id)
                attachment.status = "failed_storage"
                attachment.failure_code = "reservation_expired"
                attachment.reservation_expires_at = None
                failed_scanning += 1
        elif attachment.status == "promoting":
            verified = _close_verified_clean(storage, namespace, attachment)
            if not verified and attachment.sha256 is not None and attachment.byte_size is not None:
                try:
                    storage.promote(namespace, attachment.attachment_id, attachment.sha256, attachment.byte_size)
                except (OSError, ValueError):
                    pass
                verified = _close_verified_clean(storage, namespace, attachment)
            if verified:
                attachment.status = "available"
                promoted += 1
            else:
                _discard_inflight(storage, namespace, attachment.attachment_id)
                attachment.status = "failed_storage"
                attachment.failure_code = "recovery_failed"
                attachment.reservation_expires_at = None
                failed_promoting += 1
        elif attachment.status == "purging":
            # Retry only a prior retention purge. User-requested purging has no
            # expiry cause and must never acquire a phantom expiry audit.
            if attachment.failure_code == "expired":
                await _ensure_expiry_audit(db, attachment)
                await db.commit()
            _discard_inflight(storage, namespace, attachment.attachment_id)
            attachment.status = "purged"
            attachment.deleted_at = now
            purged += 1
        elif attachment.status in {"rejected_malware", "rejected_scanner", "failed_storage", "purged"}:
            _discard_inflight(storage, namespace, attachment.attachment_id)

    unreferenced = 0
    for area in ("staging", "clean"):
        for attachment_id in storage.list_attachment_ids(namespace, area):
            if attachment_id not in referenced_ids:
                storage.remove(namespace, attachment_id, area)
                unreferenced += 1
    await db.commit()
    return ReconcileStats(
        promoted=promoted,
        failed_scanning=failed_scanning,
        failed_promoting=failed_promoting,
        purged=purged,
        unreferenced_objects=unreferenced,
    )


async def reconcile_live_namespace(
    db: AsyncSession,
    namespace: AttachmentNamespace,
    storage: PrivateAttachmentStorage,
    *,
    now: datetime,
) -> ReconcileStats:
    """Serialize a live-namespace repair with the normal attachment pipeline."""
    from app.services.agent_runtime.task_attachments import maintenance_pipeline_lock

    async with maintenance_pipeline_lock(db):
        return await _reconcile_live_namespace_unlocked(db, namespace, storage, now=now)


async def reconcile_disposed_namespace(
    platform_db: AsyncSession,
    disposal: TenantAttachmentStorageDisposal,
    storage: PrivateAttachmentStorage,
) -> ReconcileStats:
    """Remove only after a fresh platform session observes committed authority."""
    if not isinstance(disposal, TenantAttachmentStorageDisposal):
        raise ValueError("typed disposal authority is required")
    disposal_id = disposal.disposal_id
    bind = platform_db.bind
    if bind is None or not hasattr(bind, "connect"):
        raise RuntimeError("disposed attachment reconciliation requires an engine-bound platform session")
    async with AsyncSession(bind=bind, expire_on_commit=False) as authority_db:
        durable = await authority_db.get(TenantAttachmentStorageDisposal, disposal_id)
    if durable is None or durable.reason not in {"test_rebuild", "tenant_destroyed"}:
        return ReconcileStats()
    namespace = _namespace_for_disposal(durable)
    removed = storage.remove_namespace(namespace)
    return ReconcileStats(disposed_namespaces=int(removed))


async def reconcile_configured_storage() -> ReconcileStats:
    """Reconcile configured storage once; preserve every unknown namespace."""
    if not settings.AGENT_TASK_ATTACHMENT_STORAGE_ROOT:
        raise RuntimeError("attachment storage is unavailable")
    storage = PrivateAttachmentStorage(Path(settings.AGENT_TASK_ATTACHMENT_STORAGE_ROOT))
    storage.validate_root()
    from app.database import async_session, run_for_each_tenant

    stats = ReconcileStats()
    known_namespaces = set()
    present_namespaces = storage.list_namespaces()
    public = AttachmentNamespace(None, None, "public")
    async with async_session() as db:
        stats = stats.plus(await reconcile_live_namespace(db, public, storage, now=datetime.now(UTC)))
        known_namespaces.add(public.storage_namespace)
        disposals = ()
        if present_namespaces:
            disposals = (await db.scalars(
                select(TenantAttachmentStorageDisposal).where(
                    TenantAttachmentStorageDisposal.storage_namespace.in_(present_namespaces)
                )
            )).all()
        for disposal in disposals:
            namespace = _namespace_for_disposal(disposal)
            known_namespaces.add(namespace.storage_namespace)
            if namespace.storage_namespace in present_namespaces:
                stats = stats.plus(await reconcile_disposed_namespace(db, disposal, storage))

    if settings.TENANT_MODE != "single":
        async for tenant, db in run_for_each_tenant():
            binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")
            if db.info.get("tenant_binding") not in (None, binding):
                raise RuntimeError("tenant recovery session binding changed")
            db.info["tenant_binding"] = binding
            known_rows = (await db.execute(
                select(
                    AgentTaskAttachment.tenant_id,
                    AgentTaskAttachment.origin_generation,
                    AgentTaskAttachment.storage_namespace,
                ).distinct()
            )).all()
            namespaces = {
                AttachmentNamespace(
                    tenant_id=row.tenant_id,
                    origin_generation=row.origin_generation,
                    storage_namespace=row.storage_namespace,
                )
                for row in known_rows
            }
            namespaces.add(AttachmentNamespace(
                tenant_id=tenant.id,
                origin_generation=tenant.generation,
                storage_namespace=f"tenant_{tenant.id.hex}_{tenant.generation}",
            ))
            for namespace in namespaces:
                known_namespaces.add(namespace.storage_namespace)
                try:
                    stats = stats.plus(await reconcile_live_namespace(db, namespace, storage, now=datetime.now(UTC)))
                finally:
                    db.info.pop("tenant_binding", None)
                    db.info["tenant_binding"] = binding
            db.info.pop("tenant_binding", None)

    unknown = storage.list_namespaces() - known_namespaces
    for namespace in sorted(unknown):
        logger.warning("preserving unknown historical attachment namespace %s", namespace)
    return stats.plus(ReconcileStats(preserved_unknown_namespaces=len(unknown)))
