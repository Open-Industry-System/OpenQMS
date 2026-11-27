"""Resolve authorized historical R7 result metadata without loading result bodies."""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
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
    RESULT_CONTRACT,
    PublicationScope,
    _publication_evidence,
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
        if (await _no_wait(db, statement, read=True)).scalar_one_or_none() is None:
            raise ImpactHistoryUnavailable()
    fmea_ids = {target.fmea_id} | {ref.object_id for ref in capa.sources if ref.module == "fmea"}
    for fmea_id in sorted(fmea_ids):
        if (await _no_wait(db, select(FMEADocument.fmea_id).where(
            FMEADocument.fmea_id == fmea_id,
        ), read=True)).scalar_one_or_none() is None:
            raise ImpactHistoryUnavailable()
    await lock_employee_acl(db, (reader.user.user_id,), read=True)


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
    ).limit(2), read=True)).all()
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


FMEA_IMPACT_PROJECTION = "fmea.pfmea_impact.snapshot.v1"


async def _approved_node_name(db: AsyncSession, binding: ImpactTaskBinding, node_id: str) -> str:
    """Extract one stable name from the exact approved snapshot, with bounded text."""
    from sqlalchemy import text

    rows = (await db.execute(text("""
        SELECT CASE WHEN octet_length(n->>'name') <= 16384 THEN n->>'name' END AS name
        FROM fmea_versions AS version
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(version.snapshot->'nodes') = 'array'
              THEN version.snapshot->'nodes' ELSE '[]'::jsonb END
        ) AS nodes(n)
        WHERE version.version_id = :version_id AND version.fmea_id = :fmea_id
          AND version.sha256_hash = :digest AND n->>'id' = :node_id
        LIMIT 2
    """), {
        "version_id": binding.target.approved_version_id, "fmea_id": binding.target.fmea_id,
        "digest": binding.target.snapshot_hash, "node_id": node_id,
    })).all()
    if len(rows) != 1 or not isinstance(rows[0].name, str) or len(rows[0].name.encode()) > 16 * 1024:
        raise ImpactHistoryUnavailable()
    return rows[0].name


async def authorize_history_projection_sources(
    db: AsyncSession, _: RequestScope, binding: ImpactTaskBinding, sources: frozenset[ImpactSourceRef],
) -> bool:
    """Admit only target refs minted by the R7 snapshot projection.

    This runs after current reviewer permission and exact snapshot integrity
    checks, under the historical read transaction's existing source locks.
    """
    from uuid import uuid5

    target = binding.target
    for ref in sources:
        if (
            ref.module != "fmea" or ref.projection_id != FMEA_IMPACT_PROJECTION
            or (ref.object_id, ref.snapshot_id, ref.version) != (
                target.fmea_id, target.approved_version_id, target.snapshot_hash,
            )
            or ref.source_version_counter is not None
        ):
            return False
        if ref.node_id is None:
            if ref.source_id != target.approved_version_id:
                return False
        else:
            if ref.source_id != uuid5(target.approved_version_id, "node:" + ref.node_id):
                return False
            await _approved_node_name(db, binding, ref.node_id)
    return True


async def _historical_measure_text(db: AsyncSession, report_id: UUID, measure) -> str:
    from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Proposal
    from app.models.capa_r6 import CapaD5MeasureRevision

    if measure.formal_revision is None:
        item = CapaD5Measure
        statement = select(item.final_text).join(CapaD5Proposal, CapaD5Proposal.proposal_id == item.proposal_id).where(
            item.measure_id == measure.measure_id, CapaD5Proposal.report_id == report_id,
        )
    else:
        item = CapaD5MeasureRevision
        statement = select(item.final_text).where(item.measure_id == measure.measure_id, item.report_id == report_id,
            item.revision_id == measure.formal_revision)
    value = await db.scalar(statement.where(func.octet_length(item.final_text) <= 16 * 1024))
    if not isinstance(value, str) or not value.strip():
        raise ImpactHistoryUnavailable()
    return value


def _source_label(source: ImpactSourceRef, binding: ImpactTaskBinding) -> str:
    if source.projection_id == FMEA_IMPACT_PROJECTION:
        version = f"PFMEA v{binding.target.major_no}.0"
        return version if source.node_id is None else f"{version} · {source.node_id}"
    return source.projection_id


async def _review_payload(db: AsyncSession, lookup: HistoryLookup, *, run_id: UUID) -> dict:
    result = AgentResult
    payload = await db.scalar(select(result.payload).where(
        result.result_id == lookup.result_id, result.task_id == lookup.task_id, result.run_id == run_id,
        func.octet_length(cast(result.payload, Text)) <= 512 * 1024,
    ))
    if not isinstance(payload, dict):
        raise ImpactHistoryUnavailable()
    return payload


def _cited_refs(analysis: dict, entry: dict) -> dict[str, None]:
    return dict.fromkeys((*analysis["fact_refs"], *entry["evidence_refs"], *entry["exclusion_refs"]))


async def read_history_review(
    db: AsyncSession, reader: RequestScope, lookup: HistoryLookup, *, authorize: HistorySourceAuthority,
) -> dict:
    """Build a bounded display DTO under the same locks as metadata and evidence."""
    record = await _authorized_history(db, reader, lookup, authorize=authorize)
    payload = await _review_payload(db, lookup, run_id=record.run_id)
    binding = record.binding
    sources = {str(ref.source_id): ref for ref in record.sources}
    if len(sources) != len(record.sources):
        raise ImpactHistoryUnavailable()
    expected_measures = {(str(item.measure_id), None if item.formal_revision is None else str(item.formal_revision)): item
        for item in binding.capa.measures}
    try:
        analyses = {item["analysis_ref"]: item for item in payload["analyses"]}
        measures, consumed = [], set()
        for entry in payload["assessments"]:
            key = entry["measure_id"], entry["formal_revision"]
            if key in consumed:
                raise ImpactHistoryUnavailable()
            consumed.add(key)
            measure = expected_measures[key]
            analysis = analyses[entry["analysis_ref"]]
            facts = [_source_label(sources[ref], binding) for ref in analysis["fact_refs"]]
            references = _cited_refs(analysis, entry)
            measures.append({
                "measureId": str(measure.measure_id),
                "formalRevision": key[1],
                "text": await _historical_measure_text(db, lookup.report_id, measure),
                "conclusion": Conclusion(entry["conclusion"]).value,
                "facts": facts,
                "inference": analysis["inference"],
                "reason": analysis["reason"],
                "adjustments": [item["proposal"] for item in entry["node_adjustments"]],
                "gaps": entry["missing_information"],
                "evidence": [{"id": ref, "label": _source_label(sources[ref], binding)} for ref in references],
            })
        if consumed != expected_measures.keys():
            raise ImpactHistoryUnavailable()
    except (TypeError, KeyError, ValueError):
        raise ImpactHistoryUnavailable() from None
    return {
        "reportVersionLabel": str(binding.capa.root_revision),
        "approvedVersionLabel": f"v{binding.target.major_no}.0",
        "freshness": "stale" if await _is_stale(db, reader, record) else "current",
        "conclusion": record.conclusion.value,
        "measures": measures,
    }


async def read_history_evidence(
    db: AsyncSession, reader: RequestScope, lookup: HistoryLookup, source_id: UUID,
    *, authorize: HistorySourceAuthority,
) -> dict[str, str]:
    record = await _authorized_history(db, reader, lookup, authorize=authorize)
    matches = [ref for ref in record.sources if ref.source_id == source_id]
    if len(matches) != 1:
        raise ImpactHistoryUnavailable()
    payload = await _review_payload(db, lookup, run_id=record.run_id)
    try:
        analyses = {item["analysis_ref"]: item for item in payload["analyses"]}
        cited = any(str(source_id) in _cited_refs(analyses[item["analysis_ref"]], item)
                    for item in payload["assessments"])
    except (TypeError, KeyError, ValueError):
        raise ImpactHistoryUnavailable() from None
    if not cited:
        raise ImpactHistoryUnavailable()
    ref = matches[0]
    label = _source_label(ref, record.binding)
    if ref.projection_id == FMEA_IMPACT_PROJECTION and ref.node_id is not None:
        return {"label": label, "text": await _approved_node_name(db, record.binding, ref.node_id)}
    return {"label": label, "text": ref.version}
