"""Current-authority readonly CAPA delivery with server-owned immutable receipts."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime_event import AgentProjectionReceipt
from app.models.audit import AuditLog
from app.schemas.agent_runtime import CapaContextProjection, CapaContextQuery
from app.services import capa_agent_projection
from app.services.agent_runtime import runtime_access, task_updates
from app.services.agent_runtime.runtime_access import RuntimeIdentity


def _admit(identity: RuntimeIdentity) -> None:
    runtime_access.require_capability(identity, capa_agent_projection.PROJECTION_ID)
    runtime_access.require_delivery(identity, "internal", "masked")


def _check_projection(payload: dict, identity: RuntimeIdentity) -> None:
    # Validate the entire server-built v1 allowlist and canonical full digest;
    # the response view is selected only after this validation and final auth.
    CapaContextProjection.model_validate(payload)
    if (payload["projection_id"] != capa_agent_projection.PROJECTION_ID
            or payload["data_class"] != "internal"
            or payload["source_capa_id"] != str(identity.task.target_capa_id)
            or payload["report_id"] != str(identity.task.target_capa_id)
            or payload["factory_id"] != str(identity.task.factory_id)
            or payload["product_line_code"] != identity.target_product_line_code
            or payload["projection_digest"] != capa_agent_projection.projection_digest(
                {key: value for key, value in payload.items() if key != "projection_digest"})):
        raise PermissionError("Projection unavailable")
    lines = identity.scope.pl_scope
    if lines.mode != "ALL" and (lines.mode != "EXPLICIT" or payload["product_line_code"] not in (lines.codes or [])):
        raise PermissionError("Projection unavailable")


async def get_capa_context(db: AsyncSession, identity: RuntimeIdentity,
                           report_id: UUID | None = None, view: str = "report") -> dict:
    request = CapaContextQuery(report_id=report_id, view=view)
    current = await runtime_access.refresh_runtime_identity(db, identity)
    _admit(current)
    target_id = current.task.target_capa_id
    if request.report_id is not None and request.report_id != target_id:
        raise PermissionError("Target unavailable")
    # Unlocked initial authorization allows revocation/pause to commit while
    # the independent readonly snapshot executes. Cached scopes grant nothing.
    payload = await capa_agent_projection.build_masked_d4_projection(target_id, binding=current.binding)
    # Recheck full identity after the query, with the established mutation fence
    # and before adding any dirty receipt/audit ORM objects.
    current = await runtime_access.lock_runtime_identity(db, current)
    _admit(current)
    # Compare with the exact product line used by this final authorization,
    # never a subsequent target reread or the user's broader ALL scope.
    _check_projection(payload, current)
    receipt_id = uuid4()
    generation = 0 if current.binding is None else current.binding.generation
    receipt = AgentProjectionReceipt(receipt_id=receipt_id, task_id=current.task.task_id,
        run_id=current.run.run_id, lease_epoch=current.run.lease_epoch, tenant_generation=generation,
        source_capa_id=current.task.target_capa_id, projection_id=payload["projection_id"],
        projection_digest=payload["projection_digest"], data_class="internal", created_at=datetime.now(UTC))
    db.add(receipt)
    db.add(AuditLog(table_name="agent_projection_receipts", record_id=receipt_id,
        action="QUERY_AGENT_CAPA_CONTEXT", operated_by=current.task.executor_user_id,
        factory_id=current.task.factory_id, correlation_id=current.run.run_id,
        changed_fields={"receipt_id": str(receipt_id), "task_id": str(current.task.task_id),
            "run_id": str(current.run.run_id), "executor_user_id": str(current.task.executor_user_id),
            "lease_epoch": current.run.lease_epoch, "tenant_generation": generation,
            "source_capa_id": payload["source_capa_id"], "projection_id": payload["projection_id"],
            "projection_digest": payload["projection_digest"], "outcome": "delivered"}))
    result = {**payload, "receipt_id": str(receipt_id)}
    if request.view == "report":
        del result["verifications"]
    # Receipt and safe audit are persisted in this caller-owned task transaction;
    # no content is returned if either write/commit fails.
    await db.commit()
    return result


def _recognized_source(receipt: AgentProjectionReceipt, task_id: UUID,
                       run_id: UUID, target_id: UUID, generation: int | None,
                       epoch: int | None = None) -> None:
    """Only the server-owned summary receipt is a source, never client labels."""
    import re
    from app.services.agent.permissions.catalog import get_capability
    from app.core.permissions import Module

    spec = get_capability(receipt.projection_id)
    if (receipt.task_id != task_id or receipt.run_id != run_id
            or receipt.source_capa_id != target_id
            or (generation is not None and receipt.tenant_generation != generation)
            or (epoch is not None and receipt.lease_epoch != epoch)
            or receipt.projection_id != capa_agent_projection.PROJECTION_ID
            or spec is None or spec.owner != Module.CAPA or spec.kind != "context"
            or spec.projection != "masked" or receipt.data_class != "internal"
            or not isinstance(receipt.projection_digest, str)
            or re.fullmatch(r"[a-f0-9]{64}", receipt.projection_digest) is None):
        raise PermissionError("Source unavailable")


async def _sources(db: AsyncSession, receipt_ids: list[UUID], task_id: UUID,
                   run_id: UUID, target_id: UUID, generation: int | None,
                   epoch: int | None = None) -> list[AgentProjectionReceipt]:
    from sqlalchemy import select

    identifiers = sorted(set(receipt_ids), key=str)
    with db.no_autoflush:
        rows = list((await db.scalars(select(AgentProjectionReceipt).where(
            AgentProjectionReceipt.receipt_id.in_(identifiers))
            .order_by(AgentProjectionReceipt.receipt_id)
            .execution_options(populate_existing=True))).all())
    if len(rows) != len(identifiers):
        raise PermissionError("Source unavailable")
    for receipt in rows:
        _recognized_source(receipt, task_id, run_id, target_id, generation, epoch)
    return rows


def _source_metadata(receipts: list[AgentProjectionReceipt]) -> list[dict]:
    return [{"receipt_id": str(row.receipt_id), "source_capa_id": str(row.source_capa_id),
        "projection_id": row.projection_id, "projection_digest": row.projection_digest,
        "data_class": row.data_class} for row in receipts]


async def _stored_sources(db: AsyncSession, association, id_column, output_id: UUID) -> list[UUID]:
    from sqlalchemy import select
    with db.no_autoflush:
        return list((await db.scalars(select(association.receipt_id).where(id_column == output_id)
            .order_by(association.receipt_id))).all())


def _output(row, receipts: list[AgentProjectionReceipt], *, event: bool) -> dict:
    from app.schemas.agent_runtime import RuntimeEventOut, RuntimeResultOut

    result = {"task_id": str(row.task_id), "run_id": str(row.run_id),
        "payload": row.payload, "sources": _source_metadata(receipts)}
    if event:
        result.update(event_id=str(row.event_id), event_type=row.event_type)
        return RuntimeEventOut.model_validate(result).model_dump(mode="json")
    result.update(result_id=str(row.result_id), data_class=row.data_class)
    return RuntimeResultOut.model_validate(result).model_dump(mode="json")


async def _save_output(db: AsyncSession, identity: RuntimeIdentity, body, *, event: bool) -> dict:
    from sqlalchemy import select
    from app.models.agent_runtime_event import AgentRunEvent, AgentResult, AgentEventReceipt, AgentResultReceipt
    from app.schemas.agent_runtime import RuntimeEventCreate, RuntimeResultCreate

    request = (RuntimeEventCreate if event else RuntimeResultCreate).model_validate(body)
    current = await runtime_access.lock_runtime_identity(db, identity)
    _admit(current)
    generation = 0 if current.binding is None else current.binding.generation
    receipts = await _sources(db, request.receipt_ids, current.task.task_id, current.run.run_id,
        current.task.target_capa_id, generation, current.run.lease_epoch)
    # Receipt reads can wait: full fresh authority is the final pre-mutation
    # boundary, including on an idempotent response. No dirty objects yet.
    current = await runtime_access.refresh_runtime_identity(db, current)
    _admit(current)
    for receipt in receipts:
        _recognized_source(receipt, current.task.task_id, current.run.run_id,
            current.task.target_capa_id, generation, current.run.lease_epoch)
    model, association = (AgentRunEvent, AgentEventReceipt) if event else (AgentResult, AgentResultReceipt)
    id_column = association.event_id if event else association.result_id
    payload = request.payload.model_dump(mode="json")
    identifiers = sorted({receipt.receipt_id for receipt in receipts}, key=str)
    with db.no_autoflush:
        existing = await db.scalar(select(model).where(model.run_id == current.run.run_id,
            model.idempotency_key == request.idempotency_key).execution_options(populate_existing=True))
    if existing is not None:
        output_id = existing.event_id if event else existing.result_id
        stored_ids = await _stored_sources(db, association, id_column, output_id)
        if (existing.task_id != current.task.task_id or existing.payload != payload
                or stored_ids != identifiers or (event and existing.event_type != request.event_type)
                or (not event and existing.data_class != "restricted")):
            raise ValueError("Idempotency key reused with different output")
        result = _output(existing, receipts, event=event)
        await db.commit()
        return result
    output_id = uuid4()
    fields = dict(task_id=current.task.task_id, run_id=current.run.run_id,
        idempotency_key=request.idempotency_key, payload=payload)
    if event:
        fields.update(event_id=output_id, event_type=request.event_type)
    else:
        fields.update(result_id=output_id, data_class="restricted")
    row = model(**fields)
    # Serialize/validate before mutation; unrelated constraint failures propagate.
    result = _output(row, receipts, event=event)
    db.add(row)
    await db.flush()
    db.add_all([association(**{"event_id" if event else "result_id": output_id,
        "receipt_id": receipt_id}) for receipt_id in identifiers])
    db.add(AuditLog(table_name=model.__tablename__, record_id=output_id,
        action="RECORD_AGENT_RUN_EVENT" if event else "SAVE_AGENT_RESULT",
        operated_by=current.task.executor_user_id, factory_id=current.task.factory_id,
        correlation_id=current.run.run_id, changed_fields={
            "event_id" if event else "result_id": str(output_id),
            "task_id": str(current.task.task_id), "run_id": str(current.run.run_id),
            "executor_user_id": str(current.task.executor_user_id),
            "lease_epoch": current.run.lease_epoch, "tenant_generation": generation,
            "data_class": "restricted", "sources": _source_metadata(receipts)}))
    await task_updates.append_update(db, task_id=current.task.task_id,
        kind="event" if event else "result", object_id=output_id)
    await db.commit()
    return result


async def record_event(db: AsyncSession, identity: RuntimeIdentity, body) -> dict:
    """Persist bounded progress/query events using current receipt authority."""
    return await _save_output(db, identity, body, event=True)


async def save_result(db: AsyncSession, identity: RuntimeIdentity, body) -> dict:
    """Free candidate explanations are restricted, independently of source label."""
    return await _save_output(db, identity, body, event=False)


async def admit_historical_sources(db, scope, task, run_id, identifiers,
                                   generation=None, epoch=None):
    """Reload actual source bindings and current ACL; saved versions grant nothing."""
    from app.core.permissions import Module
    from app.services.agent.permissions.delivery import SourceLabel, derive_label, can_view_derived
    from app.services.agent_runtime import task_service

    if not 1 <= len(identifiers) <= 20:
        raise PermissionError("Source unavailable")
    receipts = await _sources(db, identifiers, task.task_id, run_id,
        task.target_capa_id, generation, epoch)
    labels, authorized = [], set()
    for receipt in receipts:
        try:
            source = await task_service.require_current_capa_view(db, scope, receipt.source_capa_id)
        except LookupError:
            raise PermissionError("Source unavailable") from None
        if source.factory_id != task.factory_id:
            raise PermissionError("Source unavailable")
        labels.append(SourceLabel(Module.CAPA, receipt.source_capa_id,
            receipt.projection_digest, receipt.data_class))
        authorized.add((Module.CAPA, receipt.source_capa_id, receipt.data_class))
    if not can_view_derived(derive_label(tuple(labels)), True, frozenset(authorized)):
        raise PermissionError("Source unavailable")
    return receipts


async def _historical_output(db, scope, task_id, output_id, *, event):
    from sqlalchemy import select
    from app.models.agent_runtime_event import AgentResult, AgentResultReceipt, AgentRunEvent, AgentEventReceipt
    from app.models.agent_task import AgentRun
    from app.services.agent_runtime import task_service
    from app.services.agent_runtime.task_controls import _task_binding

    task = await task_service.get_task_for_view(db, scope, task_id)
    binding = _task_binding(task)
    model, association = (AgentRunEvent, AgentEventReceipt) if event else (AgentResult, AgentResultReceipt)
    pk = model.event_id if event else model.result_id
    link = association.event_id if event else association.result_id
    with db.no_autoflush:
        row = await db.scalar(select(model).where(pk == output_id, model.task_id == task_id)
            .execution_options(populate_existing=True))
        if row is None:
            raise LookupError("Output not found")
        run = await db.scalar(select(AgentRun).where(AgentRun.run_id == row.run_id)
            .execution_options(populate_existing=True))
    if (run is None or run.task_id != task_id
            or run.installation_id != task.preferred_installation_id
            or (not event and row.data_class != "restricted")
            or (event and row.event_type not in ("progress", "query_completed"))):
        raise PermissionError("Source unavailable")
    identifiers = await _stored_sources(db, association, link, output_id)
    if event and row.event_type == "progress" and not identifiers:
        # No receipt means no plugin-supplied text or counters may be presented.
        result = dict(event_id=str(row.event_id), task_id=str(task_id), run_id=str(row.run_id),
            event_type="progress", presentation_code="plugin_running", created_at=row.created_at,
            sources=[])
    else:
        receipts = await admit_historical_sources(db, scope, task, row.run_id, identifiers)
        result = _output(row, receipts, event=event)
        if event:
            result["data_class"] = "restricted"
    final_task = await task_service.get_task_for_view(db, scope, task_id)
    if _task_binding(final_task) != binding:
        raise PermissionError("Source unavailable")
    if identifiers:
        # Fresh actual receipts, not labels materialized before a waiting read.
        receipts = await admit_historical_sources(db, scope, final_task, row.run_id, identifiers)
        result["sources"] = _source_metadata(receipts)
    final_task = await task_service.get_task_for_view(db, scope, task_id)
    if _task_binding(final_task) != binding:
        raise PermissionError("Source unavailable")
    return result


async def get_result_for_view(db: AsyncSession, scope, task_id: UUID, result_id: UUID) -> dict:
    """Historical user view depends on current ownership and source access only."""
    return await _historical_output(db, scope, task_id, result_id, event=False)


async def get_event_for_view(db: AsyncSession, scope, task_id: UUID, event_id: UUID) -> dict:
    """Source-bound text or fixed unsourced progress, independent of plugin lease."""
    return await _historical_output(db, scope, task_id, event_id, event=True)
