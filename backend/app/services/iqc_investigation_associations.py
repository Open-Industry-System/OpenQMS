"""Exact IQC investigation links visible to the current tenant actor."""
from collections import defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Literal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.core.permissions import Module, PermissionLevel
from app.models.capa import CAPAEightD
from app.models.iqc_inspection import IqcInspection
from app.models.supplier import SupplierSCAR
from app.services.capa_current_access import current_module_access
from app.services.capa_d4_material import authorize_root
from app.services.capa_legacy_capture import authorize_bound_sources

MAX_ASSOCIATIONS = 100
MAX_FAMILY_IDS = 100
MAX_SUMMARY_CHARS = 240


class AssociationChanged(ValueError):
    """A linked investigation changed during the scoped lookup."""


@dataclass(frozen=True)
class LinkedInvestigation:
    kind: Literal["scar", "capa"]
    object_id: UUID
    number: str
    status: str
    summary: str
    inspection_ids: tuple[UUID, ...]
    linked_ids: tuple[UUID, ...]
    version: str

    @property
    def href(self) -> str:
        return f"/{'scars' if self.kind == 'scar' else 'capa'}/{self.object_id}"


@dataclass(frozen=True)
class AssociationSnapshot:
    investigations: tuple[LinkedInvestigation, ...]
    version: str
    complete: bool
    ambiguous: bool
    allowed_modules: tuple[str, ...]

    @property
    def may_consider_new(self) -> bool:
        return self.complete and not self.ambiguous and not self.investigations


def _digest(value) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(body.encode()).hexdigest()


def _line_filter(stmt, model, allowed_lines):
    if allowed_lines is None:
        return stmt
    column = model.product_line_code
    condition = column.in_(sorted(line for line in allowed_lines if line is not None))
    if None in allowed_lines:
        condition = or_(condition, column.is_(None))
    return stmt.where(condition)


def _scoped_lines(scope_lines, fresh_lines, allowed_lines):
    for lines in (scope_lines, fresh_lines):
        if lines.mode != "ALL":
            visible = frozenset(lines.codes or ()) if lines.mode == "EXPLICIT" else frozenset()
            allowed_lines = visible if allowed_lines is None else allowed_lines & visible
    return allowed_lines


def _associations(family, scars, capas, allowed_modules):
    complete = len(allowed_modules) == 2 and len(scars) + len(capas) <= MAX_ASSOCIATIONS
    # Reserve space for the SCARs that can establish a CAPA's IQC origin.
    # Construct evidence and edges only from rows included in this receipt.
    scars = scars[:MAX_ASSOCIATIONS]
    capas = capas[:MAX_ASSOCIATIONS - len(scars)]
    targets = {row.inspection_id for row in family}
    scar_ids = {row.scar_id for row in scars}
    capa_ids = {row.report_id for row in capas}
    scar_to_iqc = defaultdict(set)
    capa_to_iqc = defaultdict(set)
    for row in family:
        if row.linked_scar_id in scar_ids:
            scar_to_iqc[row.linked_scar_id].add(row.inspection_id)
        if row.linked_capa_id in capa_ids:
            capa_to_iqc[row.linked_capa_id].add(row.inspection_id)

    pairs = set()
    for row in scars:
        if row.source_type == "iqc" and row.source_id in targets:
            scar_to_iqc[row.scar_id].add(row.source_id)
        if row.capa_ref_id in capa_ids:
            pairs.add((row.scar_id, row.capa_ref_id))
    pairs.update((row.scar_ref_id, row.report_id) for row in capas if row.scar_ref_id in scar_ids)
    scar_to_capa = defaultdict(set)
    capa_to_scar = defaultdict(set)
    for scar_id, capa_id in pairs:
        scar_to_capa[scar_id].add(capa_id)
        capa_to_scar[capa_id].add(scar_id)
        capa_to_iqc[capa_id].update(scar_to_iqc[scar_id])

    # Hidden targets never become graph edges, version inputs, or ambiguity markers.
    ambiguous = any(len(ids) > 1 for ids in [*scar_to_capa.values(), *capa_to_scar.values()])
    investigations = []
    for row in scars:
        refs = tuple(sorted(scar_to_iqc[row.scar_id]))
        links = tuple(sorted(scar_to_capa[row.scar_id]))
        version = _digest((row.created_at, row.scar_no, row.status, row.summary, refs, links))
        investigations.append(LinkedInvestigation(
            "scar", row.scar_id, row.scar_no, row.status, row.summary, refs, links, version,
        ))
    for row in capas:
        refs = tuple(sorted(capa_to_iqc[row.report_id]))
        links = tuple(sorted(capa_to_scar[row.report_id]))
        version = _digest((row.created_at, row.document_no, row.status, row.title, refs, links))
        investigations.append(LinkedInvestigation(
            "capa", row.report_id, row.document_no, row.status, row.title, refs, links, version,
        ))

    investigations.sort(key=lambda item: (item.kind, item.object_id))
    records = tuple(investigations)
    version = _digest((allowed_modules, complete, ambiguous, [asdict(item) for item in records]))
    return AssociationSnapshot(records, version, complete, ambiguous, allowed_modules)


async def _visible_capas(db, scope, factory_id, lines, direct_ids, scars):
    visible_scar_ids = {row.scar_id for row in scars}
    routes = or_(
        CAPAEightD.report_id.in_(direct_ids | {row.capa_ref_id for row in scars if row.capa_ref_id}),
        CAPAEightD.scar_ref_id.in_(visible_scar_ids),
    )
    candidates = _line_filter(
        select(CAPAEightD.report_id, CAPAEightD.scar_ref_id).where(
            CAPAEightD.factory_id == factory_id, routes,
        ).order_by(CAPAEightD.report_id),
        CAPAEightD, lines,
    )
    found = []
    for candidate in (await db.execute(candidates)).all():
        try:
            await authorize_root(db, scope.user.user_id, candidate.report_id)
            await authorize_bound_sources(db, scope.user.user_id, candidate.report_id, d_step="d5")
        except (PermissionError, LookupError):
            continue
        summary = _line_filter(
            select(CAPAEightD.report_id, CAPAEightD.scar_ref_id, CAPAEightD.created_at,
                   CAPAEightD.document_no, CAPAEightD.title, CAPAEightD.status).where(
                CAPAEightD.report_id == candidate.report_id, CAPAEightD.factory_id == factory_id, routes,
            ),
            CAPAEightD, lines,
        )
        row = (await db.execute(summary)).one_or_none()
        if row is None:
            raise AssociationChanged()
        previous_edge = candidate.scar_ref_id if candidate.scar_ref_id in visible_scar_ids else None
        current_edge = row.scar_ref_id if row.scar_ref_id in visible_scar_ids else None
        if current_edge != previous_edge:
            raise AssociationChanged()
        found.append(row)
        if len(found) > MAX_ASSOCIATIONS:
            break
    return found


async def _visible_scars(db, factory_id, lines, family, targets):
    links = {row.linked_scar_id for row in family if row.linked_scar_id is not None}
    stmt = select(
        SupplierSCAR.scar_id, SupplierSCAR.scar_no,
        func.substr(SupplierSCAR.description, 1, MAX_SUMMARY_CHARS).label("summary"),
        SupplierSCAR.status, SupplierSCAR.created_at, SupplierSCAR.source_type,
        SupplierSCAR.source_id, SupplierSCAR.capa_ref_id,
    ).where(SupplierSCAR.factory_id == factory_id, or_(
        SupplierSCAR.scar_id.in_(links),
        (SupplierSCAR.source_type == "iqc") & SupplierSCAR.source_id.in_(targets),
    )).order_by(SupplierSCAR.scar_id).limit(MAX_ASSOCIATIONS + 1)
    return (await db.execute(_line_filter(stmt, SupplierSCAR, lines))).all()


async def read_linked_investigations(
    db: AsyncSession,
    scope: RequestScope,
    inspection_ids: tuple[UUID, ...],
    *,
    factory_id: UUID,
    allowed_product_lines: frozenset[str | None] | None = None,
) -> AssociationSnapshot:
    """Read links for the caller's previously authorized and resolved IQC family.

    This read has no persistence side effects. The caller owns the association
    receipt and any transactional fence around publishing the result.
    """
    targets = frozenset(inspection_ids)
    if not targets or len(targets) > MAX_FAMILY_IDS:
        raise ValueError("Invalid IQC family")

    with db.no_autoflush:
        levels, factories, fresh_lines = await current_module_access(
            db, scope, Module.IQC, PermissionLevel.VIEW,
        )
        if (scope.effective_factory_id not in (None, factory_id)
                or any(resolved.accessible_factory_ids is not None
                       and factory_id not in resolved.accessible_factory_ids
                       for resolved in (scope.factory_scope, factories))):
            raise PermissionError("IQC_ASSOCIATION_UNAVAILABLE")
        lines = _scoped_lines(scope.pl_scope, fresh_lines, allowed_product_lines)
        stmt = select(
            IqcInspection.inspection_id, IqcInspection.linked_capa_id, IqcInspection.linked_scar_id,
        ).where(IqcInspection.factory_id == factory_id, IqcInspection.inspection_id.in_(targets))
        family = (await db.execute(_line_filter(stmt, IqcInspection, lines))).all()
        if len(family) != len(targets):
            raise PermissionError("IQC_ASSOCIATION_UNAVAILABLE")

        modules = tuple(module.value for module in (Module.SCAR, Module.CAPA)
                        if levels.get(module, PermissionLevel.NONE) >= PermissionLevel.VIEW)
        scars = []
        if Module.SCAR in modules:
            scars = await _visible_scars(db, factory_id, lines, family, targets)
        capas = []
        if Module.CAPA in modules:
            direct_ids = {row.linked_capa_id for row in family if row.linked_capa_id is not None}
            capas = await _visible_capas(db, scope, factory_id, lines, direct_ids, scars)
        return _associations(family, scars, capas, modules)
