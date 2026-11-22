"""Authorized snapshots of the formal IQC facts used in investigations."""
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.deps import RequestScope
from app.core.factory_scope import is_factory_visible
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.models.audit import AuditLog
from app.models.iqc_inspection import IqcInspection
from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement
from app.models.product_line import ProductLine

INSPECTION_FIELDS = (
    "inspection_id", "inspection_no", "identity_generation", "inspection_revision",
    "factory_id", "product_line_code", "supplier_id", "material_id", "part_no",
    "part_name", "lot_no", "lot_qty", "inspection_mode", "status", "inspection_result",
    "inspection_date", "inspected_by", "judged_at", "judged_by", "defect_description",
    "defect_qty", "sample_qty", "aql_level", "inspection_level", "sampling_standard",
    "code_letter", "accept_number", "reject_number", "parent_inspection_id",
    "re_inspection", "has_safety_defect",
)
ITEM_FIELDS = (
    "item_id", "sort_order", "category", "item_name", "inspect_type", "spec_upper",
    "spec_lower", "target_value", "sample_size", "accept_no", "reject_no",
    "defect_qty", "result", "remark",
)
MEASUREMENT_FIELDS = (
    "measurement_id", "sequence_no", "measured_value", "attribute_result", "remark",
)
MAX_FAMILY = 100
MAX_PAGE = 40
MAX_CONTEXT_ITEMS = 20


class InvestigationNotReadable(ValueError):
    pass


@dataclass(frozen=True)
class InspectionMember:
    inspection_id: UUID
    identity_generation: UUID
    inspection_revision: int


@dataclass(frozen=True)
class InspectionFacts:
    payload: dict
    members: tuple[InspectionMember, ...]
    version: str
    family_complete: bool

    @property
    def family_ids(self) -> tuple[UUID, ...]:
        return tuple(member.inspection_id for member in self.members)

    @property
    def eligibility_reason(self) -> str | None:
        state, outcome = self.payload["status"], self.payload["inspection_result"]
        if state in {"pending", "inspecting"} or outcome == "pending":
            return "pending_inspection"
        if outcome == "accepted":
            return "accepted_inspection"
        if state not in {"judged", "closed"} or outcome not in {"rejected", "concession"} or self.payload["judged_at"] is None:
            return "unverified_disposition"
        return None

    @property
    def eligible(self) -> bool:
        return self.eligibility_reason is None


@dataclass(frozen=True)
class FactPage:
    rows: tuple[dict, ...]
    next_offset: int | None


def _wire(value):
    if isinstance(value, (UUID, date, datetime)):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _payload(row, fields: tuple[str, ...]) -> dict:
    return {name: _wire(row[name]) for name in fields}


async def _authorize(db, scope, row, *, allow_unassigned_line: bool) -> None:
    if not is_factory_visible(row.factory_id, scope):
        raise InvestigationNotReadable("Inspection is not readable")
    line = row.product_line_code
    lines = scope.pl_scope
    if line is None:
        if allow_unassigned_line and lines.mode == "ALL":
            return
        raise InvestigationNotReadable("Inspection is not readable")
    if lines.mode != "ALL" and (
        lines.mode != "EXPLICIT" or line not in (lines.codes or ())
    ):
        raise InvestigationNotReadable("Inspection is not readable")
    if await db.scalar(select(ProductLine.factory_id).where(ProductLine.code == line)) != row.factory_id:
        raise InvestigationNotReadable("Inspection is not readable")


async def read_inspection_facts(
    db: AsyncSession,
    scope: RequestScope,
    inspection_id: UUID,
    *,
    allow_unassigned_line: bool = False,
) -> InspectionFacts:
    """Read the bounded inspection family in the caller's tenant transaction."""
    if await get_user_permission(scope.user, Module.IQC, db) < PermissionLevel.VIEW:
        raise InvestigationNotReadable("Inspection is not readable")

    anchor_scope = (await db.execute(
        select(IqcInspection.factory_id, IqcInspection.product_line_code)
        .where(IqcInspection.inspection_id == inspection_id)
    )).one_or_none()
    if anchor_scope is None:
        raise InvestigationNotReadable("Inspection is not readable")
    await _authorize(db, scope, anchor_scope, allow_unassigned_line=allow_unassigned_line)

    columns = tuple(getattr(IqcInspection, name) for name in INSPECTION_FIELDS)
    anchor = select(
        IqcInspection.inspection_id, IqcInspection.parent_inspection_id,
        IqcInspection.factory_id, IqcInspection.product_line_code,
    ).where(
        IqcInspection.inspection_id == inspection_id,
        IqcInspection.factory_id == anchor_scope.factory_id,
        IqcInspection.product_line_code.is_not_distinct_from(anchor_scope.product_line_code),
    ).cte("anchor")
    family = select(anchor.c.inspection_id, anchor.c.parent_inspection_id).cte(
        "inspection_family", recursive=True,
    )
    neighbor = aliased(IqcInspection)
    family = family.union(
        select(neighbor.inspection_id, neighbor.parent_inspection_id)
        .join(family, or_(
            neighbor.inspection_id == family.c.parent_inspection_id,
            neighbor.parent_inspection_id == family.c.inspection_id,
        ))
        .join(anchor, and_(
            neighbor.factory_id == anchor.c.factory_id,
            neighbor.product_line_code.is_not_distinct_from(anchor.c.product_line_code),
        ))
    )
    rows = (await db.execute(
        select(*columns, IqcInspection.created_at).join(family, IqcInspection.inspection_id == family.c.inspection_id)
        .order_by((IqcInspection.inspection_id != inspection_id), IqcInspection.inspection_id)
        .limit(MAX_FAMILY + 1)
    )).mappings().all()
    if not rows:
        raise InvestigationNotReadable("Inspection is not readable")
    members = rows[:MAX_FAMILY]
    facts = [_payload(row, INSPECTION_FIELDS) for row in members]
    complete = len(rows) <= MAX_FAMILY
    visible_ids = {member["inspection_id"] for member in facts}
    for member in facts:
        if member["parent_inspection_id"] not in visible_ids:
            member["parent_inspection_id"] = None
    primary = facts[0]
    if primary["inspection_result"] == "concession":
        transition = AuditLog.changed_fields["inspection_result"]
        previous = await db.scalar(select(AuditLog.log_id).where(
            AuditLog.table_name == "iqc_inspections", AuditLog.record_id == inspection_id,
            AuditLog.action == "UPDATE", AuditLog.operated_at >= members[0].created_at,
            or_(AuditLog.factory_id.is_(None), AuditLog.factory_id == anchor_scope.factory_id),
            transition["before"].astext == "rejected", transition["after"].astext == "concession",
        ).limit(1))
        if previous is not None:
            primary["prior_inspection_result"] = "rejected"
        description = primary["defect_description"] or ""
        # The concession service appends its reason to the observation column.
        # Keep that reason out of the formal defect observation and D2.
        primary["defect_description"] = (
            None if description.startswith("让步接收原因: ")
            else description.split("; 让步接收: ", 1)[0] or None
        )
    version = hashlib.sha256(
        json.dumps([facts, complete], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload = dict(facts[0])
    payload["family_complete"] = complete
    payload["family"] = [
        {
            key: member[key]
            for key in (
                "inspection_id", "inspection_no", "inspection_date",
                "inspection_result", "status", "judged_at", "parent_inspection_id",
            )
        }
        for member in facts
    ]
    bound = tuple(
        InspectionMember(row.inspection_id, row.identity_generation, row.inspection_revision)
        for row in members
    )
    item = IqcInspectionItem
    measurement = IqcItemMeasurement
    count = select(func.count(measurement.measurement_id)).where(
        measurement.item_id == item.item_id, measurement.factory_id == item.factory_id,
    ).correlate(item).scalar_subquery()
    item_headers = (await db.execute(select(
        item.item_id, item.item_name, item.inspect_type, item.result, count.label("measurement_count"),
    ).where(
        item.inspection_id == inspection_id, item.factory_id == anchor_scope.factory_id,
        _member_guard(bound[0]).exists(),
    ).order_by(item.sort_order, item.item_id).limit(MAX_CONTEXT_ITEMS + 1))).mappings().all()
    if await db.scalar(_member_guard(bound[0])) is None:
        raise InvestigationNotReadable("Inspection detail changed")
    payload["item_summaries"] = [
        _payload(header, ("item_id", "item_name", "inspect_type", "result", "measurement_count"))
        for header in item_headers[:MAX_CONTEXT_ITEMS]
    ]
    payload["item_summaries_truncated"] = len(item_headers) > MAX_CONTEXT_ITEMS
    return InspectionFacts(payload, bound, version, complete)


def _member_guard(member: InspectionMember):
    return select(IqcInspection.inspection_id).where(
        IqcInspection.inspection_id == member.inspection_id,
        IqcInspection.identity_generation == member.identity_generation,
        IqcInspection.inspection_revision == member.inspection_revision,
    )


async def read_item_page(
    db: AsyncSession,
    facts: InspectionFacts,
    inspection_id: UUID,
    *,
    item_id: UUID | None = None,
    offset: int = 0,
    limit: int = MAX_PAGE,
) -> FactPage:
    """Use only a server-bound facts snapshot and cursor from the same run."""
    member = next((entry for entry in facts.members if entry.inspection_id == inspection_id), None)
    if member is None or offset < 0 or not 1 <= limit <= MAX_PAGE:
        raise InvestigationNotReadable("Inspection detail is not readable")

    guard = _member_guard(member)
    item = IqcInspectionItem
    match = (item.inspection_id == inspection_id, item.factory_id == UUID(facts.payload["factory_id"]))
    if item_id is None:
        fields = ITEM_FIELDS
        query = (
            select(*(getattr(item, name) for name in fields)).where(*match)
            .order_by(item.sort_order, item.item_id)
        )
    else:
        measurement = IqcItemMeasurement
        fields = MEASUREMENT_FIELDS
        query = (
            select(*(getattr(measurement, name) for name in fields))
            .join(item, and_(measurement.item_id == item.item_id, measurement.factory_id == item.factory_id))
            .where(*match, item.item_id == item_id)
            .order_by(measurement.sequence_no, measurement.measurement_id)
        )
    rows = (await db.execute(
        query.where(guard.exists()).offset(offset).limit(limit + 1)
    )).mappings().all()
    if await db.scalar(guard) is None:
        raise InvestigationNotReadable("Inspection detail changed")
    return FactPage(
        tuple(_payload(row, fields) for row in rows[:limit]),
        offset + limit if len(rows) > limit else None,
    )
