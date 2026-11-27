"""Publish immutable IQC investigation cards and authorize historical review."""
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import Module, PermissionLevel
from app.models.agent_iqc_investigation import IqcInvestigationReceipt
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.supplier import SupplierSCAR
from app.models.user import User
from app.services.agent_runtime.control_authority_fence import ControlFenceBusy, lock_employee_acl
from app.services.capa_current_access import current_module_access
from app.services.iqc_investigation_actions import (
    InvestigationAction, read_review_investigation_hint, validate_investigation_action,
)
from app.services.iqc_investigation_associations import read_linked_investigations
from app.services.iqc_investigation_facts import read_inspection_facts, read_item_page
from app.services.iqc_investigation_optional import (
    HISTORY_PROJECTION, MATERIAL_PROJECTION, SUPPLIER_PROJECTION, HistoryCursor,
    read_current_material, read_current_supplier, read_inspection_history,
)

RESULT_CONTRACT = "iqc_investigation_result.v1"
CONTEXT = "iqc.inspection.context.v1"
ITEMS = "iqc.inspection.items.v1"
REINSPECTION = "iqc.inspection.reinspection_chain.v1"
ASSOCIATIONS = "iqc.investigation.associations.v1"
MAX_RECEIPTS = 64


class IqcResultUnavailable(PermissionError):
    """The requested run, result, or source is no longer authorized."""


class MissingItem(StrEnum):
    OBJECT = "missing_object"
    BATCH = "missing_batch"
    TIME = "missing_time"
    OBSERVATION = "missing_observation"
    SAMPLE_QTY = "sample_qty_unrecorded"
    REINSPECTION = "reinspection_unconfirmed"
    MEASUREMENTS = "measurement_details_unavailable"
    SUPPLIER = "supplier_information_unavailable"
    ASSOCIATIONS = "investigation_check_incomplete"
    CONFLICT = "inspection_record_conflict"
    SPEC_LIMITS = "measurement_limits_conflict"
    HISTORY = "history_unavailable"
    MATERIAL = "material_information_unavailable"
    BUDGET = "source_budget_exhausted"


class NextStep(StrEnum):
    INSPECTION = "confirm_inspection_record"
    SAMPLE = "confirm_sample_extent"
    MEASUREMENT = "verify_measurement_method"
    LOT = "check_lot_status"
    SUPPLIER = "review_supplier_evidence"
    REINSPECTION = "review_reinspection"


class IqcResultCard(BaseModel):
    """Only codes and receipt IDs can originate in the model's proposal."""

    model_config = ConfigDict(extra="forbid")

    action: InvestigationAction
    evidence_refs: tuple[UUID, ...] = Field(min_length=1, max_length=MAX_RECEIPTS)
    missing: tuple[MissingItem, ...] = Field(default=(), max_length=len(MissingItem))
    next_steps: tuple[NextStep, ...] = Field(default=(), max_length=len(NextStep))
    include_d2: StrictBool = True


def _json_document(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, default=str))


def _digest(value):
    return sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def _snapshot_wire(snapshot):
    return _json_document(asdict(snapshot))


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _observations(facts, selected):
    recorded = _text(facts.get("defect_description"))
    notes = [f"单据现象记录：「{recorded}」"] if recorded else []
    items = {}
    for row in selected:
        projection, _, data, params = _source_fields(row)
        if projection == ITEMS and params.get("inspection_id") == facts["inspection_id"] and params.get("item_id") is None:
            items.update((item["item_id"], item) for item in data["rows"])
    inconsistent_limits = {
        item_id for item_id, item in items.items()
        if item["spec_lower"] is not None and item["spec_upper"] is not None
        and item["spec_lower"] > item["spec_upper"]
    }
    for item in items.values():
        if len(notes) >= 4:
            break
        if item.get("inspect_type") == "attribute" and item.get("result") == "rejected" and _text(item.get("item_name")):
            notes.append(f"项目「{item['item_name']}」的定性判定记录为不合格")
    measured = {}
    for row in selected:
        projection, _, data, params = _source_fields(row)
        if (projection != ITEMS or params.get("inspection_id") != facts["inspection_id"]
                or params.get("item_id") not in items):
            continue
        readings = measured.setdefault(params["item_id"], {})
        readings.update((item["measurement_id"], item["measured_value"]) for item in data["rows"])
    for item_id, readings in measured.items():
        if len(notes) >= 4:
            break
        if item_id in inconsistent_limits:
            continue
        item = items[item_id]
        lower, upper = item["spec_lower"], item["spec_upper"]
        outliers = [
            value for value in readings.values()
            if value is not None and ((lower is not None and value < lower) or (upper is not None and value > upper))
        ]
        if not outliers:
            continue
        examples = "、".join(str(value) for value in outliers[:3])
        limits = "，".join(
            f"{label} {value}" for label, value in (("下限", lower), ("上限", upper)) if value is not None
        )
        notes.append(
            f"按已存规格核对，项目 {item['item_name']} 的已读实测记录有 {len(outliers)} 条超限（{limits}），"
            f"其中记录值为 {examples}"
        )
    return notes, bool(inconsistent_limits)


def _d2_text(facts, missing, observations, supplier):
    if {
        MissingItem.OBJECT, MissingItem.BATCH, MissingItem.TIME,
        MissingItem.OBSERVATION, MissingItem.REINSPECTION,
    } & set(missing):
        return None
    part = " / ".join(dict.fromkeys(filter(None, (_text(facts.get("part_no")), _text(facts.get("part_name"))))))
    template = f"{part}，批次 {_text(facts.get('lot_no'))}，来料检验单 {facts['inspection_no']}。"
    if facts.get("inspection_date"):
        template += f"检验日期 {facts['inspection_date']}。"
    if facts.get("judged_at"):
        template += f"判定时间 {facts['judged_at']}。"
    if facts.get("inspection_result") == "concession":
        outcome = "让步接收"
    elif facts.get("inspection_result") == "rejected":
        outcome = "拒收"
    else:
        return None
    if facts.get("prior_inspection_result") == "rejected":
        template += f"原判定为拒收，当前判定为{outcome}。"
    else:
        template += f"检验单判定为{outcome}。"
    template += "。".join(observations) + "。"
    if supplier:
        template += f"本单供应商引用的当前名称为「{supplier}」。"
    sample = facts.get("sample_qty")
    template += f"单据记录抽样量 {sample}。" if sample is not None and sample > 0 else "抽样量未记录。"
    return template + "所述现象限于检验记录，超限记录数不能直接换算为不合格件数，整批实际不合格数量及原因尚待核实。"


def _disposition_changed(facts):
    return facts["inspection_result"] == "concession" or any(
        member["parent_inspection_id"] is not None
        and member["status"] in {"judged", "closed"}
        and member["inspection_result"] in {"accepted", "concession"}
        for member in facts["family"]
    )


def _details_incomplete(facts, selected):
    summaries = facts.get("item_summaries", [])
    if not summaries or facts.get("item_summaries_truncated"):
        return True
    items = set()
    measurements = {}
    for row in selected:
        projection, _, data, params = _source_fields(row)
        if projection != ITEMS or params["inspection_id"] != facts["inspection_id"]:
            continue
        item_id = params["item_id"]
        if item_id is None:
            items.update(record["item_id"] for record in data["rows"])
        else:
            measurements.setdefault(item_id, set()).update(record["measurement_id"] for record in data["rows"])
    return any(
        summary["item_id"] not in items
        or len(measurements.get(summary["item_id"], ())) < summary["measurement_count"]
        for summary in summaries
    )


def _derived_missing(facts, selected, projections, association, observations):
    missing = set()
    if not (_text(facts.get("part_no")) or _text(facts.get("part_name"))):
        missing.add(MissingItem.OBJECT)
    if not _text(facts.get("lot_no")):
        missing.add(MissingItem.BATCH)
    if not (facts.get("inspection_date") or facts.get("judged_at")):
        missing.add(MissingItem.TIME)
    if not observations:
        missing.add(MissingItem.OBSERVATION)
    if facts.get("inspection_result") == "rejected" and facts.get("defect_qty") == 0:
        missing.add(MissingItem.CONFLICT)
    if facts.get("sample_qty") is None or facts["sample_qty"] <= 0:
        missing.add(MissingItem.SAMPLE_QTY)
    if not facts.get("family_complete") or any(
        item["status"] not in {"judged", "closed"} for item in facts.get("family", [])
    ):
        missing.add(MissingItem.REINSPECTION)
    if facts.get("inspection_mode") == "detailed" and _details_incomplete(facts, selected):
        missing.add(MissingItem.MEASUREMENTS)
    if SUPPLIER_PROJECTION not in projections:
        missing.add(MissingItem.SUPPLIER)
    if association is None or not association.complete or association.ambiguous:
        missing.add(MissingItem.ASSOCIATIONS)
    return missing


def _render_card(proposal, receipts, facts, association, query_gaps):
    ref_set = {row.receipt_id for row in receipts}
    if len(set(proposal.evidence_refs)) != len(proposal.evidence_refs) or not set(proposal.evidence_refs) <= ref_set:
        raise ValueError("Unknown or repeated IQC evidence reference")
    selected = [row for row in receipts if row.receipt_id in proposal.evidence_refs]
    evidence_types = {row.payload["projection"] for row in selected}
    if CONTEXT not in evidence_types:
        raise ValueError("A formal IQC inspection reference is required")
    if proposal.action is not InvestigationAction.CHECK_EXISTING and ASSOCIATIONS not in evidence_types:
        raise ValueError("An investigation association reference is required")
    validate_investigation_action(proposal.action, association)
    observations, inconsistent_limits = _observations(facts, selected)
    supplier = next((
        _text(row.payload["data"].get("name")) for row in selected
        if row.payload["projection"] == SUPPLIER_PROJECTION
    ), "")
    missing = set(proposal.missing) | _derived_missing(facts, selected, evidence_types, association, observations)
    if inconsistent_limits:
        missing.add(MissingItem.SPEC_LIMITS)
    for projection, reason in query_gaps:
        if reason == "budget_exhausted":
            missing.add(MissingItem.BUDGET)
        if projection == HISTORY_PROJECTION:
            missing.add(MissingItem.HISTORY)
        if projection == MATERIAL_PROJECTION:
            missing.add(MissingItem.MATERIAL)
        if projection == REINSPECTION and REINSPECTION not in evidence_types:
            missing.add(MissingItem.REINSPECTION)
    changed = _disposition_changed(facts)
    action = proposal.action
    if action is InvestigationAction.CONSIDER_NEW and (changed or MissingItem.REINSPECTION in missing):
        action = InvestigationAction.CHECK_EXISTING
    return {
        "action": action.value,
        "facts": {**facts, "disposition_changed": changed},
        "missing": sorted(missing),
        "next_steps": list(dict.fromkeys(proposal.next_steps)),
        "d2": _d2_text(facts, missing, observations, supplier) if proposal.include_d2 else None,
    }


async def _fresh_employee_scope(db, scope):
    _, factories, lines = await current_module_access(db, scope, Module.IQC, PermissionLevel.VIEW)
    previous_ids = scope.factory_scope.accessible_factory_ids
    if previous_ids is not None:
        ids = factories.accessible_factory_ids
        factories = FactoryScope(
            previous_ids if ids is None else sorted(set(ids) & set(previous_ids)),
            factories.default_factory_id,
        )
    if scope.pl_scope.mode != "ALL":
        known = set(scope.pl_scope.codes or ()) if scope.pl_scope.mode == "EXPLICIT" else set()
        if lines.mode != "ALL":
            known &= set(lines.codes or ()) if lines.mode == "EXPLICIT" else set()
        lines = ProductLineScope("EXPLICIT" if known else "NONE", sorted(known))
    employee = await db.get(User, scope.user.user_id, populate_existing=True)
    if employee is None or not employee.is_active:
        raise IqcResultUnavailable("IQC employee unavailable")
    return replace(scope, user=employee, factory_scope=factories, pl_scope=lines)


async def _load_receipts(db, task_id, run_id, lease_epoch):
    receipt = IqcInvestigationReceipt
    rows = tuple((await db.scalars(select(receipt).where(
        receipt.task_id == task_id,
        receipt.run_id == run_id,
        receipt.lease_epoch == lease_epoch,
        receipt.kind == "source",
    ).order_by(receipt.receipt_id).limit(MAX_RECEIPTS + 1))).all())
    if len(rows) > MAX_RECEIPTS:
        raise IqcResultUnavailable("Too many IQC sources")
    return rows


def _source_fields(row):
    payload = row.payload
    if not isinstance(payload, dict):
        raise IqcResultUnavailable("Invalid IQC source")
    projection = payload.get("projection")
    version = payload.get("version")
    data = payload.get("data")
    params = payload.get("params")
    if (
        projection not in {CONTEXT, ITEMS, REINSPECTION, ASSOCIATIONS, HISTORY_PROJECTION,
                           MATERIAL_PROJECTION, SUPPLIER_PROJECTION}
        or not isinstance(version, str) or not isinstance(data, dict) or not isinstance(params, dict)
    ):
        raise IqcResultUnavailable("Invalid IQC source")
    return projection, version, data, params


def _as_uuid(value):
    return UUID(str(value))


def _history_cursor(params):
    raw = params.get("cursor")
    return HistoryCursor(date.fromisoformat(raw["inspection_date"]), _as_uuid(raw["inspection_id"])) if raw else None


async def _live_source(db, scope, facts, projection, params, *, association_family=None):
    inspection_id = _as_uuid(facts.payload["inspection_id"])
    if projection in {CONTEXT, REINSPECTION}:
        return facts.version, facts.payload, None
    if projection == ITEMS:
        page = await read_item_page(
            db, facts, _as_uuid(params["inspection_id"]),
            item_id=_as_uuid(params["item_id"]) if params.get("item_id") is not None else None,
            offset=params["offset"], limit=params["limit"],
        )
        data = _snapshot_wire(page)
        return _digest(data), data, None
    if projection == ASSOCIATIONS:
        raw = params["product_lines"]
        if raw is not None and (not isinstance(raw, list) or any(x is not None and not isinstance(x, str) for x in raw)):
            raise IqcResultUnavailable("Invalid IQC association scope")
        allowed = frozenset(raw) if raw is not None else None
        if scope.pl_scope.mode != "ALL" and (
            allowed is None or not allowed <= set(scope.pl_scope.codes or ())
        ):
            raise IqcResultUnavailable("Association scope unavailable")
        snapshot = await read_linked_investigations(
            db, scope, association_family or facts.family_ids,
            factory_id=_as_uuid(facts.payload["factory_id"]), allowed_product_lines=allowed,
        )
        return snapshot.version, _snapshot_wire(snapshot), snapshot
    if projection == HISTORY_PROJECTION:
        page = await read_inspection_history(
            db, scope, inspection_id, task_date=date.fromisoformat(params["task_date"]),
            cursor=_history_cursor(params), limit=params["limit"],
        )
        if page is None:
            raise IqcResultUnavailable("Inspection history unavailable")
        data = _snapshot_wire(page)
        return _digest(data), data, None

    reader = read_current_material if projection == MATERIAL_PROJECTION else read_current_supplier
    summary = await reader(db, scope, inspection_id)
    if summary is None:
        raise IqcResultUnavailable("Current master data unavailable")
    return summary.source.version, _snapshot_wire(summary), None


async def _checked_sources(db, scope, receipts, facts):
    association = None
    for row in receipts:
        projection, version, data, params = _source_fields(row)
        actual_version, actual, snapshot = await _live_source(db, scope, facts, projection, params)
        # Check the exact released body, not only a hash or item cursor.
        if version != actual_version or data != actual:
            raise IqcResultUnavailable("IQC source changed")
        if projection in {CONTEXT, REINSPECTION}:
            if set(_historic_family(row.payload, facts)) != set(facts.family_ids):
                raise IqcResultUnavailable("IQC inspection family changed")
        if projection == ASSOCIATIONS:
            association = snapshot
    return association


_SOURCE_ERRORS = (PermissionError, HTTPException, LookupError, TypeError, ValueError)


async def recheck_iqc_receipts(db, scope, task_id, run_id, lease_epoch, facts):
    """Reauthorize all receipts already released to an active run."""
    try:
        rows = await _load_receipts(db, task_id, run_id, lease_epoch)
        scope = await _fresh_employee_scope(db, scope)
        await _checked_sources(db, scope, rows, facts)
        return rows
    except _SOURCE_ERRORS as exc:
        raise IqcResultUnavailable("IQC delivery sources unavailable") from exc


async def read_query_gaps(db, run_id, epoch):
    fields = AuditLog.changed_fields
    return (await db.execute(select(fields["projection"].astext, fields["reason"].astext).distinct().where(
        AuditLog.correlation_id == run_id, AuditLog.action == "IQC_QUERY_UNAVAILABLE",
        fields["lease_epoch"].astext == str(epoch),
    ))).all()


async def _bound_facts(db, scope, binding):
    return await read_inspection_facts(
        db, scope, _as_uuid(binding["inspection_id"]),
        allow_unassigned_line=binding["allow_unassigned_line"],
    )


def _active(task, run, epoch):
    return (
        task.status == "ready" and run.status == "active" and run.lease_epoch == epoch
        and run.lease_expires_at is not None and run.lease_expires_at > datetime.now(UTC)
    )


async def publish_iqc_investigation_result(
    db: AsyncSession,
    scope: RequestScope,
    task_id: UUID,
    run_id: UUID,
    lease_epoch: int,
    *,
    operation_key: str,
    card: IqcResultCard,
) -> UUID:
    """Publish in the authenticated runtime's transaction, without committing it."""
    from app.services.agent_runtime.iqc_investigation_tasks import load_iqc_binding, lock_iqc_associations
    from app.services.agent_runtime import task_updates

    if not isinstance(card, IqcResultCard) or not isinstance(operation_key, str) or (
        not operation_key.strip() or len(operation_key) > 100 or "\0" in operation_key
    ):
        raise ValueError("Invalid IQC result submission")
    request_digest = _digest(card.model_dump(mode="json"))

    with db.no_autoflush:
        await lock_iqc_associations(db)
        task = await db.scalar(select(AgentTask).where(
            AgentTask.task_id == task_id,
        ).with_for_update().execution_options(populate_existing=True))
        run = await db.scalar(select(AgentRun).where(
            AgentRun.run_id == run_id,
        ).with_for_update().execution_options(populate_existing=True))
        if (
            task is None or run is None or run.task_id != task_id
            or task.executor_user_id != scope.user.user_id
            or run.installation_id != task.preferred_installation_id
        ):
            raise IqcResultUnavailable("IQC run unavailable")
        replay = (
            task.status == run.status == "completed" and run.lease_epoch == lease_epoch + 1
            and run.lease_expires_at is None and run.claim_key is None
        )
        if not replay and not _active(task, run, lease_epoch):
            raise IqcResultUnavailable("IQC run unavailable")
        _, row = await load_iqc_binding(db, task_id)
        binding = row.binding
        try:
            await lock_employee_acl(db, [scope.user.user_id], read=True)
            scope = await _fresh_employee_scope(db, scope)
            facts = await _bound_facts(db, scope, binding)
            if facts.version != binding["facts_version"] or not facts.eligible:
                raise IqcResultUnavailable("IQC facts changed")
            rows = await _load_receipts(db, task_id, run_id, lease_epoch)
            association = await _checked_sources(db, scope, rows, facts)
        except (*_SOURCE_ERRORS, ControlFenceBusy) as exc:
            raise IqcResultUnavailable("IQC publication sources unavailable") from exc
        previous = (await db.scalars(select(AgentResult).where(
            AgentResult.task_id == task_id, AgentResult.run_id == run_id,
        ).limit(2))).all()

    receipt_ids = [str(item.receipt_id) for item in rows]
    gaps = await read_query_gaps(db, run_id, lease_epoch)
    rendered = _render_card(card, rows, facts.payload, association, gaps)
    payload = {
        "contract": RESULT_CONTRACT, "binding_digest": row.binding_digest, "lease_epoch": lease_epoch,
        "action": rendered["action"], "request_digest": request_digest, "receipt_ids": receipt_ids,
        "card": rendered,
    }
    if replay:
        if len(previous) != 1 or previous[0].idempotency_key != operation_key or previous[0].payload != payload:
            raise ValueError("IQC result key already used")
        return previous[0].result_id
    if previous or not _active(task, run, lease_epoch):
        raise IqcResultUnavailable("IQC run unavailable")

    result_id = uuid4()
    async with db.begin_nested():
        db.add(AgentResult(
            result_id=result_id, task_id=task_id, run_id=run_id, idempotency_key=operation_key,
            data_class="restricted", payload=payload,
        ))
        await db.flush()
        task.status = run.status = "completed"
        run.lease_epoch += 1
        run.lease_expires_at = None
        run.claim_key = None
        db.add(AuditLog(
            table_name="agent_results", record_id=result_id, action="COMPLETE_AGENT_IQC_INVESTIGATION",
            factory_id=task.factory_id, operated_by=task.executor_user_id, correlation_id=run_id,
            changed_fields={"task_id": str(task_id), "run_id": str(run_id), "status": "completed"},
        ))
        await task_updates.append_update(db, task_id=task_id, kind="result", object_id=result_id)
        await db.flush()
    return result_id


def _association_entries(data):
    return {
        (item["kind"], _as_uuid(item["object_id"])): item
        for item in data["investigations"]
    }


def _historic_family(context, facts):
    original = context["params"]["members"]
    if not isinstance(original, list) or not original or len(original) > 100:
        raise IqcResultUnavailable("Original IQC source identity unavailable")
    current = {member.inspection_id: member.identity_generation for member in facts.members}
    original_ids = tuple(_as_uuid(item["inspection_id"]) for item in original)
    if len(original_ids) != len(set(original_ids)) or not set(original_ids) <= set(current):
        raise IqcResultUnavailable("Original IQC source unavailable")
    if any(current[_as_uuid(item["inspection_id"])] != _as_uuid(item["identity_generation"]) for item in original):
        raise IqcResultUnavailable("Original IQC source identity changed")
    source = context["data"]
    if (source["inspection_id"] != facts.payload["inspection_id"]
            or source["identity_generation"] != facts.payload["identity_generation"]):
        raise IqcResultUnavailable("Historic inspection identity changed")
    return original_ids


async def _author_scope(db, scope, author_id):
    if scope.user.user_id == author_id:
        return scope
    user = await db.get(User, author_id, populate_existing=True)
    if user is None:
        return None
    try:
        return await _fresh_employee_scope(db, replace(
            scope, user=user, factory_scope=FactoryScope(None, None),
            pl_scope=ProductLineScope("ALL", None),
        ))
    except PermissionError:
        # The historical card belongs to the reader's current authorization.
        # A departed or revoked author cannot provide a fresh comparison.
        return None


async def _verify_association_identity(db, facts, original):
    """Rebuild the historic summary version with the currently authorized row's identity."""
    factory_id = _as_uuid(facts.payload["factory_id"])
    projections = (
        ("scar", SupplierSCAR, SupplierSCAR.scar_id),
        ("capa", CAPAEightD, CAPAEightD.report_id),
    )
    for kind, model, key in projections:
        items = {
            _as_uuid(item["object_id"]): item
            for item in original["investigations"]
            if item["kind"] == kind
        }
        if not items:
            continue
        generations = dict((await db.execute(select(key, model.created_at).where(
            key.in_(items), model.factory_id == factory_id,
        ))).all())
        for identity, item in items.items():
            created = generations.get(identity)
            if created is None or _digest([
                str(created), item["number"], item["status"], item["summary"],
                item["inspection_ids"], item["linked_ids"],
            ]) != item["version"]:
                raise IqcResultUnavailable("Original IQC association identity changed")


async def _association_changed(db, author, scope, facts, row, params, live):
    original = row.payload["data"]
    original_modules = set(original["allowed_modules"])
    old_entries = _association_entries(original)
    live_entries = _association_entries(live)
    if not original_modules <= set(live["allowed_modules"]) or not old_entries.keys() <= live_entries.keys():
        raise IqcResultUnavailable("Original IQC association scope unavailable")
    await _verify_association_identity(db, facts, original)
    edge_fields = ("inspection_ids", "linked_ids")
    for key, previous in old_entries.items():
        visible = live_entries[key]
        if any(visible[field] != previous[field] for field in ("number", "status", "summary")):
            return True
        if any(set(previous[field]) - set(visible[field]) for field in edge_fields):
            return True

    if author is scope:
        current = live
    elif author is None:
        return False
    else:
        try:
            _, current, _ = await _live_source(db, author, facts, ASSOCIATIONS, params)
        except _SOURCE_ERRORS:
            return False

    if not original_modules <= set(current["allowed_modules"]):
        return False
    submitted_range = _association_entries(current)
    shared = {key for key in submitted_range.keys() & live_entries.keys() if key[0] in original_modules}
    if not old_entries.keys() <= shared:
        # A change in author permissions alone does not invalidate shared facts.
        return False
    if shared != old_entries.keys():
        return True
    if current == live and set(current["allowed_modules"]) == original_modules:
        return row.payload["version"] != current["version"]

    # A row version covers its edges as seen by the actor who queried it.
    # Newly linked edges must be visible in both queries to stale a shared card.
    for key, previous in old_entries.items():
        submitted = submitted_range[key]
        visible = live_entries[key]
        if any((set(submitted[field]) & set(visible[field])) - set(previous[field]) for field in edge_fields):
            return True
    return False


async def _historical_sources(db, scope, facts, receipts, binding, author_id):
    by_context = [row for row in receipts if _source_fields(row)[0] == CONTEXT]
    if not by_context or any(row.payload["version"] != binding["facts_version"] for row in by_context):
        raise IqcResultUnavailable("Original IQC inspection unavailable")
    original_ids = _historic_family(by_context[0].payload, facts)
    if any(_historic_family(row.payload, facts) != original_ids for row in by_context[1:]):
        raise IqcResultUnavailable("Original IQC inspection unavailable")
    stale = binding["facts_version"] != facts.version
    author = None
    if any(row.payload["projection"] == ASSOCIATIONS for row in receipts):
        author = await _author_scope(db, scope, author_id)
    for row in receipts:
        projection, version, data, params = _source_fields(row)
        if projection in {CONTEXT, REINSPECTION}:
            if version != binding["facts_version"] or _historic_family(row.payload, facts) != original_ids:
                raise IqcResultUnavailable("Original IQC family unavailable")
            continue
        if projection == ITEMS and stale:
            # Items belong to the historic inspection snapshot. Its current
            # identity and the original family authority were checked above.
            if _as_uuid(params["inspection_id"]) not in original_ids or _digest(data) != version:
                raise IqcResultUnavailable("Original IQC item unavailable")
            continue
        actual_version, actual, _ = await _live_source(
            db, scope, facts, projection, params,
        )
        if projection == ASSOCIATIONS:
            changed = await _association_changed(db, author, scope, facts, row, params, actual)
            stale = stale or changed
        elif version != actual_version or data != actual:
            # A historical page or master data body with an unproven source
            # generation cannot be shared on the strength of its old receipt.
            raise IqcResultUnavailable("Original optional IQC source unavailable")
    return stale


async def get_iqc_investigation_result(
    db: AsyncSession, scope: RequestScope, task_id: UUID, result_id: UUID,
) -> dict:
    """Return the immutable original and the current employee's private hint."""
    from app.services.agent_runtime.iqc_investigation_tasks import load_iqc_binding

    try:
        with db.no_autoflush:
            task, bind = await load_iqc_binding(db, task_id)
            if task.status != "completed":
                raise IqcResultUnavailable("IQC result unavailable")
            await lock_employee_acl(db, (scope.user.user_id, task.executor_user_id), read=True)
            scope = await _fresh_employee_scope(db, scope)
            facts = await _bound_facts(db, scope, bind.binding)
            if not (
                facts.payload["factory_id"] == bind.binding["factory_id"]
                and facts.payload["product_line_code"] == bind.binding["product_line_code"]
                and facts.payload["identity_generation"] == bind.binding["identity_generation"]
            ):
                raise IqcResultUnavailable("IQC inspection moved")
            result = AgentResult
            meta = (await db.execute(select(
                result.run_id, result.created_at, result.payload["lease_epoch"].as_integer().label("epoch"),
                result.payload["receipt_ids"].label("receipts"),
            ).join(AgentRun, AgentRun.run_id == result.run_id).where(
                AgentRun.task_id == task_id,
                AgentRun.status == "completed",
                AgentRun.lease_epoch == result.payload["lease_epoch"].as_integer() + 1,
                result.result_id == result_id,
                result.task_id == task_id,
                result.data_class == "restricted",
                result.payload["contract"].astext == RESULT_CONTRACT,
                result.payload["binding_digest"].astext == bind.binding_digest,
            ))).one_or_none()
            if meta is None or type(meta.epoch) is not int or not isinstance(meta.receipts, list):
                raise IqcResultUnavailable("IQC result unavailable")
            rows = await _load_receipts(db, task_id, meta.run_id, meta.epoch)
            if {str(row.receipt_id) for row in rows} != set(meta.receipts) or len(rows) != len(meta.receipts):
                raise IqcResultUnavailable("Original IQC source manifest unavailable")
            stale = await _historical_sources(db, scope, facts, rows, bind.binding, task.executor_user_id)
            payload = await db.scalar(select(result.payload).where(
                result.result_id == result_id, result.task_id == task_id,
            ))
            if not isinstance(payload, dict) or not isinstance(payload.get("card"), dict):
                raise IqcResultUnavailable("IQC result unavailable")
            recorded = InvestigationAction(payload["action"])
            hint = await read_review_investigation_hint(
                db, scope, recorded=recorded, is_current=not stale, inspection_ids=facts.family_ids,
                factory_id=_as_uuid(bind.binding["factory_id"]),
            )
    except (*_SOURCE_ERRORS, ControlFenceBusy) as exc:
        raise LookupError("IQC result unavailable") from exc

    card = dict(payload["card"])
    card["evidence"] = [{
        "receipt_id": str(item.receipt_id),
        "projection": item.payload["projection"],
        "version": item.payload["version"],
        "data": item.payload["data"],
    } for item in rows]
    return {
        "result_id": str(result_id),
        "task_id": str(task_id),
        "created_at": meta.created_at.isoformat(),
        "model_deployment": {"name": bind.binding["deployment_name"], "version": bind.binding["deployment_version"]}
        if bind.binding.get("deployment_name") and bind.binding.get("deployment_version") else None,
        "stale": stale,
        "card": card,
        "current_hint": {
            "action": hint.action.value,
            "investigations": [
                {**_snapshot_wire(item), "href": item.href} for item in hint.investigations
            ],
            "checked_modules": list(hint.checked_modules),
        },
    }
