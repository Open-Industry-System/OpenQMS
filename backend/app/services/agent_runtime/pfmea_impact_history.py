"""Resolve authorized historical R7 result metadata without loading result bodies."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
import re
from uuid import UUID

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.models.agent_pfmea_impact import AgentPfmeaImpactBinding, AgentPfmeaImpactResultReceipt
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.schemas.pfmea_impact import ImpactSourceRef
from app.services import capa_impact_material
from app.services.agent_runtime.control_authority_fence import ControlFenceBusy, _no_wait, lock_employee_acl
from app.services.agent_runtime.pfmea_impact_completion import Conclusion
from app.services.agent_runtime.pfmea_impact_results import (
    RESULT_CONTRACT, PublicationScope, _publication_evidence,
)
from app.services.agent_runtime.pfmea_impact_tasks import ImpactTaskBinding, load_binding
from app.services.fmea_agent_sources import visible_fmea_source
from app.services.fmea_impact_projection import read_approved_target


class ImpactHistoryUnavailable(PermissionError):
    def __init__(self):
        super().__init__("Impact result unavailable")


@dataclass(frozen=True, slots=True)
class HistoryLookup:
    report_id: UUID
    task_id: UUID
    result_id: UUID


@dataclass(frozen=True, slots=True)
class HistoryMetadata:
    report_id: UUID
    task_id: UUID
    result_id: UUID
    run_id: UUID
    fmea_id: UUID
    approved_version_id: UUID
    major_no: int
    conclusion: Conclusion
    stale: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class _ResolvedHistory:
    lookup: HistoryLookup
    run_id: UUID
    epoch: int
    binding: ImpactTaskBinding
    original_hash: str
    conclusion: Conclusion
    created_at: datetime
    receipt_ids: frozenset[UUID]
    sources: frozenset[ImpactSourceRef]


# The additional projection registry is owned by the runtime, not the request.
# This callback must reauthorize each extra reference against its immutable
# historical version while the service's employee and document locks are held.
HistorySourceAuthority = Callable[
    [AsyncSession, RequestScope, ImpactTaskBinding, frozenset[ImpactSourceRef]], Awaitable[bool],
]


async def _load_history(db: AsyncSession, lookup: HistoryLookup) -> _ResolvedHistory:
    result, task, run, bind = AgentResult, AgentTask, AgentRun, AgentPfmeaImpactBinding
    row = (await db.execute(select(
        result.run_id, result.created_at, result.data_class,
        result.payload["contract"].astext.label("contract"),
        result.payload["binding_digest"].astext.label("result_binding"),
        result.payload["lease_epoch"].label("epoch"),
        result.payload["request_digest"].astext.label("request_digest"),
        result.payload["conclusion"].astext.label("conclusion"),
        bind.binding_digest, run.lease_epoch.label("terminal_epoch"), run.installation_id,
    ).join(task, result.task_id == task.task_id)
      .join(run, (run.run_id == result.run_id) & (run.task_id == task.task_id))
      .join(bind, bind.task_id == task.task_id)
      .where(
          result.result_id == lookup.result_id, task.task_id == lookup.task_id,
          task.target_capa_id == lookup.report_id, task.status == "completed", run.status == "completed",
          run.lease_expires_at.is_(None), run.claim_key.is_(None),
          run.installation_id == task.preferred_installation_id,
      ))).one_or_none()
    if (
        row is None or row.data_class != "restricted" or row.contract != RESULT_CONTRACT
        or row.result_binding != row.binding_digest
        or type(row.epoch) is not int or row.epoch < 0 or row.terminal_epoch != row.epoch + 1
        or not isinstance(row.request_digest, str) or re.fullmatch(r"[0-9a-f]{64}", row.request_digest) is None
    ):
        raise ImpactHistoryUnavailable()
    try:
        conclusion = Conclusion(row.conclusion)
    except ValueError:
        raise ImpactHistoryUnavailable() from None
    binding = await load_binding(db, lookup.task_id)
    if binding.capa.report_id != lookup.report_id or binding.activation.installation_id != row.installation_id:
        raise ImpactHistoryUnavailable()

    release_scope = PublicationScope(
        lookup.task_id, row.run_id, row.installation_id, row.epoch, row.binding_digest,
    )
    receipts, sources = await _publication_evidence(db, release_scope, binding)
    receipt_ids = frozenset(receipt.receipt_id for receipt in receipts)
    link = AgentPfmeaImpactResultReceipt
    linked = frozenset((await db.scalars(select(link.receipt_id).where(
        link.result_id == lookup.result_id,
    ).limit(len(receipt_ids) + 1))).all())
    if linked != receipt_ids:
        raise ImpactHistoryUnavailable()
    return _ResolvedHistory(
        lookup, row.run_id, row.epoch, binding, binding.target.snapshot_hash,
        conclusion, row.created_at, receipt_ids, sources,
    )


async def _authorize_bound(db: AsyncSession, reader: RequestScope, record: _ResolvedHistory) -> None:
    capa, target = record.binding.capa, record.binding.target
    await capa_impact_material.authorize_history(db, reader, capa)
    visible = await visible_fmea_source(db, reader, target.fmea_id)
    if (visible.factory_id, visible.product_line_code) != (capa.factory_id, capa.product_line_code):
        raise ImpactHistoryUnavailable()


async def _lock_history(db: AsyncSession, reader: RequestScope, record: _ResolvedHistory) -> None:
    """Lock only the exact already authorized scope, before rechecking it."""
    capa, target = record.binding.capa, record.binding.target
    required = (
        select(AgentTask.task_id).where(AgentTask.task_id == record.lookup.task_id),
        select(AgentRun.run_id).where(AgentRun.run_id == record.run_id),
        select(CAPAEightD.report_id).where(
            CAPAEightD.report_id == capa.report_id, CAPAEightD.factory_id == capa.factory_id,
            CAPAEightD.product_line_code == capa.product_line_code,
        ),
    )
    for statement in required:
        if (await _no_wait(db, statement)).scalar_one_or_none() is None:
            raise ImpactHistoryUnavailable()
    fmea_ids = {target.fmea_id} | {ref.object_id for ref in capa.sources if ref.module == "fmea"}
    for fmea_id in sorted(fmea_ids):
        if (await _no_wait(db, select(FMEADocument.fmea_id).where(
            FMEADocument.fmea_id == fmea_id,
        ))).scalar_one_or_none() is None:
            raise ImpactHistoryUnavailable()
    await lock_employee_acl(db, (reader.user.user_id,))


async def _assert_historical_target(db: AsyncSession, record: _ResolvedHistory) -> None:
    """Verify the exact historic approved scope and hash without returning a graph."""
    capa, target = record.binding.capa, record.binding.target
    if await db.scalar(select(FMEADocument.fmea_id).where(
        FMEADocument.fmea_id == target.fmea_id, FMEADocument.fmea_type == "PFMEA",
        FMEADocument.factory_id == capa.factory_id, FMEADocument.product_line_code == capa.product_line_code,
    )) is None:
        raise ImpactHistoryUnavailable()
    logs = (await _no_wait(db, select(AuditLog.factory_id, AuditLog.changed_fields).where(
        AuditLog.table_name == "fmea_versions", AuditLog.record_id == target.approved_version_id,
        AuditLog.action == "CREATE",
    ).limit(2))).all()
    if len(logs) != 1:
        raise ImpactHistoryUnavailable()
    factory_id, fields = logs[0]
    if (
        factory_id != capa.factory_id or not isinstance(fields, dict)
        or fields.get("fmea_id") != str(target.fmea_id) or fields.get("change_type") != "approve"
        or fields.get("approval_scope_v1") != {
            "product_line_code": capa.product_line_code, "snapshot_hash": record.original_hash,
        }
    ):
        raise ImpactHistoryUnavailable()
    version = FMEAVersion
    stored = await db.scalar(select(version.version_id).where(
        version.version_id == target.approved_version_id, version.fmea_id == target.fmea_id,
        version.factory_id == capa.factory_id, version.change_type == "approve",
        version.major_no == target.major_no, version.minor_no == 0,
        version.r7_approved_scope_generation == target.scope_generation,
        version.sha256_hash == record.original_hash,
        func.encode(func.public.digest(cast(version.snapshot, Text), "sha256"), "hex") == record.original_hash,
    ))
    if stored != target.approved_version_id:
        raise ImpactHistoryUnavailable()


def _additional_sources(record: _ResolvedHistory) -> frozenset[ImpactSourceRef]:
    capa, target = record.binding.capa, record.binding.target
    additional = record.sources - frozenset(capa.sources)
    for ref in additional:
        if (ref.factory_id, ref.product_line_code) != (capa.factory_id, capa.product_line_code):
            raise ImpactHistoryUnavailable()
        if ref.module == "capa":
            if ref.object_id != capa.report_id:
                raise ImpactHistoryUnavailable()
        elif (ref.object_id, ref.snapshot_id) != (target.fmea_id, target.approved_version_id):
            raise ImpactHistoryUnavailable()
    return additional


async def _is_stale(db: AsyncSession, reader: RequestScope, record: _ResolvedHistory) -> bool:
    capa, target = record.binding.capa, record.binding.target
    try:
        current_capa = (await capa_impact_material._metadata(db, reader, capa.report_id)).binding
        if current_capa != capa:
            return True
        current_target = await read_approved_target(
            db, reader, target.fmea_id, factory_id=capa.factory_id, product_line_code=capa.product_line_code,
        )
    except (PermissionError, LookupError, capa_impact_material.ImpactMaterialNotReady):
        # Current data may have changed. The exact historical binding and all
        # its permissions were already verified; do not reveal which fact changed.
        return True
    return (
        current_target.version_id != target.approved_version_id
        or current_target.scope_generation != target.scope_generation
        or current_target.sha256_hash != record.original_hash
    )


async def _authorized_history(
    db: AsyncSession, reader: RequestScope, lookup: HistoryLookup, *, authorize: HistorySourceAuthority,
) -> _ResolvedHistory:
    try:
        with db.no_autoflush:
            first = await _load_history(db, lookup)
            await _authorize_bound(db, reader, first)
            await _lock_history(db, reader, first)
            current = await _load_history(db, lookup)
            if current != first:
                raise ImpactHistoryUnavailable()
            await _authorize_bound(db, reader, current)
            await _assert_historical_target(db, current)
            additional = _additional_sources(current)
            if await authorize(db, reader, current.binding, additional) is not True:
                raise ImpactHistoryUnavailable()
            return current
    except (PermissionError, LookupError, ControlFenceBusy):
        raise ImpactHistoryUnavailable() from None


async def read_history_metadata(
    db: AsyncSession, reader: RequestScope, lookup: HistoryLookup, *, authorize: HistorySourceAuthority,
) -> HistoryMetadata:
    """Resolve metadata under final current authority in a dedicated read transaction.

    The caller must serialize the returned value before releasing the locks and
    return it only after transaction success. Never cache the authorized result
    or reuse it as authority for a different request. This function does not
    select or return the stored assessment body.
    """
    record = await _authorized_history(db, reader, lookup, authorize=authorize)
    target = record.binding.target
    return HistoryMetadata(
        lookup.report_id, lookup.task_id, lookup.result_id, record.run_id, target.fmea_id,
        target.approved_version_id, target.major_no, record.conclusion,
        await _is_stale(db, reader, record), record.created_at,
    )


async def resolve_history_source(
    db: AsyncSession, reader: RequestScope, lookup: HistoryLookup, source_id: UUID,
    *, authorize: HistorySourceAuthority,
) -> ImpactSourceRef:
    """Resolve one exact historical reference, never its current-id replacement.

    A record in the release ledger may reflect an uncertain delivery. Successful
    lookup only resolves source metadata, and does not assert confirmed coverage
    or grant authority to fetch current node content.
    """
    record = await _authorized_history(db, reader, lookup, authorize=authorize)
    matched = [ref for ref in record.sources if ref.source_id == source_id]
    if len(matched) != 1:
        raise ImpactHistoryUnavailable()
    return matched[0]
