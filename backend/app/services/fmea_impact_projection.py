"""Project a server-selected PFMEA step from an already authorized snapshot.

This module does not authorize reads or issue receipts. The runtime must resolve
the step through the formal material contract and supply confirmed page keys
from the same run, lease epoch, snapshot and scope.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.services.fmea_agent_sources import visible_fmea_source
from app.services.version_service import compute_pg_jsonb_hash, compute_snapshot_hash


FMEA_IMPACT_TARGET_CAPABILITY = "fmea.pfmea_impact.target.v1"
FMEA_IMPACT_QUERY_CAPABILITY = "fmea.pfmea_impact.query.v1"
FMEA_SNAPSHOT_PROJECTION = "fmea.pfmea_impact.snapshot.v1"


class ImpactTargetUnavailable(LookupError):
    """No currently authorized approved PFMEA target."""


class IncompleteImpactScope(ValueError):
    """The snapshot does not establish a complete, bounded failure chain."""


@dataclass(frozen=True, slots=True)
class ImpactElement:
    kind: str
    node_id: str | None = None
    name: str | None = None
    source_id: str | None = None
    target_id: str | None = None

    @property
    def accounting_key(self) -> str:
        coordinate = ("node", self.node_id) if self.node_id is not None else (
            "edge", self.kind, self.source_id, self.target_id,
        )
        return json.dumps(coordinate, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ImpactPage:
    key: str
    elements: tuple[ImpactElement, ...]

    def projection_bytes(self) -> bytes:
        """Serialize the stable page body separately from the confirmation value."""
        return json.dumps(
            {"page_key": self.key, "elements": [asdict(element) for element in self.elements]},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ApprovedImpactSnapshot:
    version_id: UUID
    major_no: int
    sha256_hash: str
    graph: dict


@dataclass(frozen=True, slots=True)
class ApprovedImpactTarget:
    fmea_id: UUID
    version_id: UUID
    major_no: int
    sha256_hash: str
    scope_generation: UUID
    document_no: str
    title: str
    has_unapproved_revision: bool


async def read_approved_target(
    db: AsyncSession,
    scope: RequestScope,
    fmea_id: UUID,
    *,
    factory_id: UUID,
    product_line_code: str,
    expected_version_id: UUID | None = None,
    lock: bool = False,
) -> ApprovedImpactTarget:
    """Check live scope and publication metadata without loading either graph."""
    try:
        visible = await visible_fmea_source(db, scope, fmea_id)
    except (PermissionError, LookupError):
        raise ImpactTargetUnavailable("Approved PFMEA unavailable") from None
    if (visible.factory_id, visible.product_line_code) != (factory_id, product_line_code):
        raise ImpactTargetUnavailable("Approved PFMEA unavailable")
    doc = FMEADocument
    statement = select(doc.document_no, doc.title, doc.status, doc.r7_scope_generation).where(
        doc.fmea_id == fmea_id, doc.fmea_type == "PFMEA", doc.factory_id == factory_id,
        doc.product_line_code == product_line_code,
    )
    if lock:
        statement = statement.with_for_update(read=True)
    target = (await db.execute(statement)).one_or_none()
    if target is None or target.r7_scope_generation is None:
        raise ImpactTargetUnavailable("Approved PFMEA unavailable")

    approved = FMEAVersion
    approved_statement = select(approved.version_id, approved.major_no, approved.sha256_hash,
        approved.r7_approved_scope_generation).where(approved.fmea_id == fmea_id, approved.factory_id == factory_id,
        approved.change_type == "approve", approved.major_no >= 1, approved.minor_no == 0,
    ).order_by(approved.major_no.desc()).limit(2)
    latest = (await db.execute(approved_statement)).all()
    if not latest or (len(latest) == 2 and latest[0].major_no == latest[1].major_no):
        raise ImpactTargetUnavailable("Approved PFMEA unavailable")
    version_id, major_no, stored_hash, approval_generation = latest[0]
    if (approval_generation != target.r7_scope_generation
            or not stored_hash or expected_version_id is not None and expected_version_id != version_id):
        raise ImpactTargetUnavailable("Approved PFMEA unavailable")
    publication = (await db.execute(
        select(AuditLog.factory_id, AuditLog.changed_fields).where(
            AuditLog.table_name == "fmea_versions",
            AuditLog.record_id == version_id,
            AuditLog.action == "CREATE",
        ).limit(2)
    )).all()
    if len(publication) != 1:
        raise ImpactTargetUnavailable("Approved PFMEA unavailable")
    published_factory, published_fields = publication[0]
    if (
        published_factory != factory_id or not isinstance(published_fields, dict)
        or published_fields.get("change_type") != "approve"
        or published_fields.get("fmea_id") != str(fmea_id)
        or published_fields.get("approval_scope_v1") != {
            "product_line_code": product_line_code, "snapshot_hash": stored_hash,
        }
    ):
        raise ImpactTargetUnavailable("Approved PFMEA unavailable")
    submitted = await db.scalar(select(approved.version_id).where(
        approved.fmea_id == fmea_id, approved.factory_id == factory_id,
        approved.change_type == "submit", approved.major_no == major_no,
    ).limit(1))
    try:
        if await visible_fmea_source(db, scope, fmea_id) != visible:
            raise ImpactTargetUnavailable("Approved PFMEA unavailable")
    except PermissionError:
        raise ImpactTargetUnavailable("Approved PFMEA unavailable") from None
    if not lock:
        # A picker does not retain an update lock on each candidate. Recheck
        # after ACL waits so an away-and-back scope move cannot reuse a label.
        generation = await db.scalar(select(doc.r7_scope_generation).where(doc.fmea_id == fmea_id))
        if generation != approval_generation or (await db.execute(approved_statement)).all() != latest:
            raise ImpactTargetUnavailable("Approved PFMEA unavailable")
    return ApprovedImpactTarget(
        fmea_id, version_id, major_no, stored_hash, approval_generation, target.document_no,
        target.title, target.status != "approved" or submitted is not None,
    )


async def read_approved_snapshot(
    db: AsyncSession,
    scope: RequestScope,
    fmea_id: UUID,
    *,
    factory_id: UUID,
    product_line_code: str,
    expected_version_id: UUID | None = None,
) -> ApprovedImpactSnapshot:
    """Read the authorized approved snapshot, holding its parent through verification."""
    target = await read_approved_target(db, scope, fmea_id, factory_id=factory_id,
        product_line_code=product_line_code, expected_version_id=expected_version_id, lock=True)
    approved = FMEAVersion
    graph = await db.scalar(select(approved.snapshot).where(
        approved.version_id == target.version_id, approved.fmea_id == fmea_id,
    ))
    if not isinstance(graph, dict):
        raise ImpactTargetUnavailable("Approved PFMEA unavailable")
    actual = await compute_pg_jsonb_hash(db, graph)
    if target.sha256_hash != actual and target.sha256_hash != compute_snapshot_hash(graph):
        raise ImpactTargetUnavailable("Approved PFMEA unavailable")
    return ApprovedImpactSnapshot(target.version_id, target.major_no, target.sha256_hash, graph)


_FUNCTION_KINDS = {"ProcessStepFunction", "ProcessWorkElementFunction"}
_OWNERS = {"ProcessStep", "ProcessWorkElement"}
_EDGE_KINDS = {
    "HAS_WORK_ELEMENT": ({"ProcessStep"}, {"ProcessWorkElement"}),
    "HAS_FUNCTION": (_OWNERS | {"ProcessItem"}, _FUNCTION_KINDS | {"ProcessItemFunction"}),
    "HAS_FAILURE_MODE": (_OWNERS | _FUNCTION_KINDS, {"FailureMode"}),
    "EFFECT_OF": ({"FailureMode"}, {"FailureEffect"}),
    "CAUSE_OF": ({"FailureCause"}, {"FailureMode"}),
    "PREVENTED_BY": ({"FailureCause", "FailureMode"}, {"PreventionControl"}),
    "DETECTED_BY": ({"FailureCause", "FailureMode"}, {"DetectionControl"}),
}
_REQUIRED_INCOMING = {
    "FailureEffect": "EFFECT_OF",
    "PreventionControl": "PREVENTED_BY",
    "DetectionControl": "DETECTED_BY",
}
_MAX_ELEMENTS = 200
_MAX_PAGES = 16
_MAX_PROJECTION_BYTES = 256 * 1024


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise IncompleteImpactScope("Invalid graph coordinate")
    return value


def _coordinates(row: dict, key: str) -> str:
    return _identifier(row.get(key))


def _snapshot_indexes(snapshot: dict):
    nodes: dict[str, tuple[str, str]] = {}
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    if not isinstance(snapshot, dict) or any(
        not isinstance(snapshot.get(key), list) for key in ("nodes", "edges")
    ):
        raise IncompleteImpactScope("Invalid PFMEA snapshot")
    for row in snapshot["nodes"]:
        if not isinstance(row, dict):
            raise IncompleteImpactScope("Invalid graph node")
        node_id = _coordinates(row, "id")
        kind = _coordinates(row, "type")
        name = row.get("name")
        if node_id in nodes or not isinstance(name, str):
            raise IncompleteImpactScope("Ambiguous graph node")
        nodes[node_id] = (kind, name)
    edges = set()
    for row in snapshot["edges"]:
        if not isinstance(row, dict):
            raise IncompleteImpactScope("Invalid graph edge")
        kind = _coordinates(row, "type")
        if kind not in _EDGE_KINDS:
            continue
        source, target = _coordinates(row, "source"), _coordinates(row, "target")
        allowed_source, allowed_target = _EDGE_KINDS[kind]
        if (
            source not in nodes or target not in nodes
            or nodes[source][0] not in allowed_source or nodes[target][0] not in allowed_target
            or (kind, source, target) in edges
        ):
            raise IncompleteImpactScope("Unresolved failure chain edge")
        edges.add((kind, source, target))
        outgoing[kind, source].append(target)
        incoming[kind, target].append(source)
    return nodes, outgoing, incoming


@dataclass(frozen=True, slots=True)
class StepDiscovery:
    elements: tuple[ImpactElement, ...]
    next_offset: int | None


def discover_snapshot_steps(
    snapshot: dict, *, term: str, offset: int = 0, page_size: int = 25,
) -> StepDiscovery:
    """List step candidates. The last discovery page is not coverage evidence."""
    if (
        not isinstance(term, str) or not term.strip() or len(term.encode("utf-8")) > 120
        or type(offset) is not int or offset < 0 or type(page_size) is not int or not 1 <= page_size <= 25
    ):
        raise ValueError("Invalid step search")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("nodes"), list):
        raise IncompleteImpactScope("Invalid PFMEA snapshot")

    term = term.strip().casefold()
    steps: dict[str, str] = {}
    seen = set()
    for row in snapshot["nodes"]:
        if not isinstance(row, dict):
            raise IncompleteImpactScope("Invalid graph node")
        node_id = _coordinates(row, "id")
        if node_id in seen:
            raise IncompleteImpactScope("Ambiguous graph node")
        seen.add(node_id)
        if row.get("type") != "ProcessStep":
            continue
        name = row.get("name")
        if not isinstance(name, str):
            raise IncompleteImpactScope("Invalid process step")
        number = row.get("process_number")
        if term in name.casefold() or (isinstance(number, str) and term == number.casefold()):
            steps[node_id] = name
    candidates = sorted(steps)
    elements = tuple(ImpactElement(kind="ProcessStep", node_id=node_id, name=steps[node_id])
                     for node_id in candidates[offset:offset + page_size])
    return StepDiscovery(elements, offset + page_size if offset + page_size < len(candidates) else None)


def plan_step_coverage(
    snapshot: dict, *, step_id: str, snapshot_digest: str, page_size: int = 25,
) -> tuple[ImpactPage, ...]:
    """Plan canonical pages for one formally identified step, with no filtering."""
    if type(page_size) is not int or not 1 <= page_size <= 25 or not snapshot_digest:
        raise ValueError("Invalid page plan binding")
    nodes, outgoing, incoming = _snapshot_indexes(snapshot)
    if step_id not in nodes or nodes[step_id][0] != "ProcessStep":
        raise IncompleteImpactScope("No exact process step")

    selected_nodes = {step_id}
    selected_edges: set[tuple[str, str, str]] = set()

    def follow(kind: str, start: str, *, reverse: bool = False) -> list[str]:
        ends = (incoming if reverse else outgoing)[kind, start]
        for end in ends:
            selected_nodes.add(end)
            selected_edges.add((kind, end, start) if reverse else (kind, start, end))
        return ends

    def owner_step(owner: str) -> str:
        kind = nodes[owner][0]
        if kind in _FUNCTION_KINDS:
            structural_owners = incoming["HAS_FUNCTION", owner]
            expected_kind = {
                "ProcessStepFunction": "ProcessStep",
                "ProcessWorkElementFunction": "ProcessWorkElement",
            }[kind]
            if len(structural_owners) != 1 or nodes[structural_owners[0]][0] != expected_kind:
                raise IncompleteImpactScope("Ambiguous function owner")
            owner = structural_owners[0]
            kind = expected_kind
        if kind == "ProcessStep":
            return owner
        parents = incoming["HAS_WORK_ELEMENT", owner]
        if len(parents) != 1:
            raise IncompleteImpactScope("Ambiguous work element owner")
        return parents[0]

    for node_id, (kind, _) in nodes.items():
        if kind == "FailureMode":
            owners = incoming["HAS_FAILURE_MODE", node_id]
            if len(owners) != 1:
                raise IncompleteImpactScope("Ambiguous failure mode owner")
            owner_step(owners[0])
        elif kind == "FailureCause" and not outgoing["CAUSE_OF", node_id]:
            raise IncompleteImpactScope("Unmapped failure cause")
        else:
            relation = _REQUIRED_INCOMING.get(kind)
            if relation is not None and not incoming[relation, node_id]:
                raise IncompleteImpactScope("Unmapped effect or control")

    owners = [step_id, *follow("HAS_WORK_ELEMENT", step_id)]
    functions = [node_id for owner in owners for node_id in follow("HAS_FUNCTION", owner)]
    modes = {mode for owner in (*owners, *functions) for mode in follow("HAS_FAILURE_MODE", owner)}
    if not modes:
        raise IncompleteImpactScope("No complete failure chain")
    for mode in modes:
        follow("EFFECT_OF", mode)
        causes = follow("CAUSE_OF", mode, reverse=True)
        if not causes:
            raise IncompleteImpactScope("Failure mode has no mapped cause")
        for owner in (mode, *causes):
            follow("PREVENTED_BY", owner)
            follow("DETECTED_BY", owner)
    if len(selected_nodes) + len(selected_edges) > _MAX_ELEMENTS:
        raise IncompleteImpactScope("Projection element budget exceeded")
    elements = [
        ImpactElement(kind=nodes[node][0], node_id=node, name=nodes[node][1])
        for node in sorted(selected_nodes)
    ]
    elements.extend(
        ImpactElement(kind=kind, source_id=source, target_id=target)
        for kind, source, target in sorted(selected_edges)
    )
    if len(elements) > _MAX_PAGES * page_size:
        raise IncompleteImpactScope("Projection page budget exceeded")

    pages = []
    total_bytes = 0
    for offset in range(0, len(elements), page_size):
        batch = tuple(elements[offset:offset + page_size])
        canonical = json.dumps(
            [
                snapshot_digest, step_id, page_size, offset,
                [(e.kind, e.node_id, e.name, e.source_id, e.target_id) for e in batch],
            ],
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        page = ImpactPage(sha256(canonical).hexdigest(), batch)
        total_bytes += len(page.projection_bytes())
        if total_bytes > _MAX_PROJECTION_BYTES:
            raise IncompleteImpactScope("Projection byte budget exceeded")
        pages.append(page)
    return tuple(pages)


def coverage_complete(pages: Iterable[ImpactPage], confirmed_page_keys: Iterable[str]) -> bool:
    """A duplicate confirmation cannot stand in for another canonical page."""
    expected = {page.key for page in pages}
    return bool(expected) and expected == set(confirmed_page_keys)


def canonical_page_digests(pages: Iterable[ImpactPage]) -> dict[str, str]:
    """Return the expected payload digest for each server-planned page key."""
    return {page.key: sha256(page.projection_bytes()).hexdigest() for page in pages}
