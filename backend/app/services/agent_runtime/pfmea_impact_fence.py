"""R7 publication evidence derived from the locked run and approved snapshot."""

import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
from uuid import UUID

from app.schemas.pfmea_impact import ImpactSourceRef
from app.services.agent_runtime.pfmea_impact_completion import MeasureKey
from app.services.agent_runtime.pfmea_impact_ledger import scope_digest
from app.services.agent_runtime.pfmea_impact_projections import (
    _bytes,
    _scope,
    _step_plan,
    read_step_handle,
    step_handle,
)
from app.services.agent_runtime.pfmea_impact_release import PageScope
from app.services.agent_runtime.pfmea_impact_results import (
    ImpactPublicationDenied,
    PublicationAuthorization,
    PublicationContext,
)
from app.services.agent_runtime.pfmea_impact_runtime import ImpactRuntime, target_source, validate_run_lifecycle
from app.services.fmea_impact_projection import ImpactElement, ImpactPage

_ADJUSTABLE = {"FailureMode", "FailureCause", "FailureEffect", "PreventionControl", "DetectionControl"}


@dataclass(frozen=True)
class _StepEvidence:
    step_id: str
    kinds: dict[str, str]
    edges: frozenset[tuple[str, str]]

    def supports(self, node_id: str, referenced: set[str]) -> bool:
        if self.kinds.get(node_id) not in _ADJUSTABLE or self.step_id not in referenced:
            return False
        outgoing = defaultdict(list)
        for start, end in self.edges:
            if start in referenced and end in referenced and start in self.kinds and end in self.kinds:
                outgoing[start].append(end)
        pending, visited = [self.step_id], set()
        while pending:
            current = pending.pop()
            if current == node_id:
                return True
            if current not in visited:
                visited.add(current)
                pending.extend(outgoing[current])
        return False


@dataclass(frozen=True)
class _EvidenceVerifier:
    capa_refs: dict[MeasureKey, frozenset[str]]
    target_ref: str | None
    target_nodes: dict[str, str]
    steps: dict[str, _StepEvidence]
    coverage: dict[str, str]
    scope_anchors: dict[MeasureKey, frozenset[str]]

    def verify_evidence(self, measure: MeasureKey, refs: tuple[str, ...]) -> bool:
        if measure not in self.capa_refs:
            return False
        return all(
            ref in self.capa_refs[measure] or ref == self.target_ref or ref in self.target_nodes for ref in refs
        )

    def verify_impact_path(self, measure: MeasureKey, target_ref: str, evidence_refs: tuple[str, ...]) -> bool:
        target = self.target_nodes.get(target_ref)
        if (target is None or target_ref not in evidence_refs or not self.verify_evidence(measure, evidence_refs)
                or not self.capa_refs[measure].intersection(evidence_refs)):
            return False
        referenced = {self.target_nodes[ref] for ref in evidence_refs if ref in self.target_nodes}
        anchors = self.scope_anchors[measure]
        return any(
            (not anchors or bool(anchors.intersection(step.kinds.keys())))
            and step.supports(target, referenced)
            for step in self.steps.values()
        )

    def verify_coverage(self, measure: MeasureKey, refs: tuple[str, ...]) -> bool:
        anchors = self.scope_anchors.get(measure)
        return bool(anchors and refs) and all(
            ref in self.coverage and bool(anchors.intersection(self.steps[self.coverage[ref]].kinds.keys()))
            for ref in refs
        )

    def verify_exclusion(self, measure: MeasureKey, refs: tuple[str, ...], coverage_refs: tuple[str, ...]) -> bool:
        # The current approved graph and CAPA projection publish no typed,
        # measure-applicable exclusion. Neither graph exhaustiveness nor model
        # interpretation of free text establishes an exclusion.
        return False


def _refs(receipt) -> frozenset[ImpactSourceRef]:
    raw = receipt.payload.get("sources")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 256:
        raise ImpactPublicationDenied("Invalid release sources")
    refs = frozenset(ImpactSourceRef.model_validate(ref) for ref in raw)
    if len(refs) != len(raw):
        raise ImpactPublicationDenied("Duplicate release sources")
    return refs


def _same_scope(row, scope: PageScope) -> bool:
    return (
        (row.task_id, row.run_id, row.lease_epoch) == (scope.task_id, scope.run_id, scope.lease_epoch)
        and row.scope_digest == scope_digest(scope)
    )


def _release_matches(row, body: bytes, keys, refs: frozenset[ImpactSourceRef]) -> bool:
    return (
        row.payload.get("payload_digest") == sha256(body).hexdigest()
        and row.payload.get("byte_count") == len(body)
        and row.payload.get("element_keys") == sorted(set(keys))
        and _refs(row) == refs
    )


def _search_nodes(current, row, refs, target, approved_nodes) -> set[str]:
    """Rebuild disclosed candidate facts without treating the search as coverage."""
    if re.fullmatch(r"search:[0-9a-f]{64}", row.payload["scope_ref"]) is None or target not in refs:
        raise ImpactPublicationDenied("Invalid target search evidence")
    nodes = set()
    for ref in refs - {target}:
        if (ref.node_id is None or approved_nodes.get(ref.node_id, (None, None))[0] != "ProcessStep"
                or ref != target_source(current.binding, ref.node_id)):
            raise ImpactPublicationDenied("Invalid target search evidence")
        nodes.add(ref.node_id)
    if len(nodes) > 25:
        raise ImpactPublicationDenied("Invalid target search evidence")
    directory = _scope(current, "directory")
    elements = [ImpactElement(kind="ProcessStep", node_id=node, name=approved_nodes[node][1])
                for node in sorted(nodes)]
    candidates = [
        {**asdict(element), "source_id": str(target_source(current.binding, element.node_id).source_id),
         "scope_ref": step_handle(directory, element.node_id)}
        for element in elements
    ]
    # The query text is deliberately not stored. An absent cursor admits
    # either truncation flag; neither affects the exact candidate facts.
    flags = (False, True) if row.payload.get("next_cursor") is None else (False,)
    if not any(_release_matches(
        row, _bytes({"candidates": candidates, "truncated": flag}),
        (element.accounting_key for element in elements), refs,
    ) for flag in flags):
        raise ImpactPublicationDenied("Invalid target search evidence")
    return nodes


def _merge_pages(step_id: str, pages) -> _StepEvidence:
    kinds, edges = {}, set()
    for page in pages:
        for element in page.elements:
            if element.node_id is not None:
                kinds[element.node_id] = element.kind
            elif element.kind == "CAUSE_OF":
                edges.add((element.target_id, element.source_id))
            else:
                edges.add((element.source_id, element.target_id))
    return _StepEvidence(step_id, kinds, frozenset(edges))


def _build(current: ImpactRuntime, receipts: tuple, sources: frozenset[ImpactSourceRef]) -> _EvidenceVerifier:
    binding, material = current.binding, current.material
    target = target_source(binding)
    base = _scope(current, "capa.material")
    if (
        material.binding != binding.capa or current.snapshot.version_id != binding.target.approved_version_id
        or current.snapshot.major_no != binding.target.major_no
        or current.snapshot.sha256_hash != binding.target.snapshot_hash
        or not 1 <= len(receipts) <= 64
    ):
        raise ImpactPublicationDenied("Invalid verified impact context")
    approved_nodes = {}
    for node in current.snapshot.graph["nodes"]:
        if node["id"] in approved_nodes:
            raise ImpactPublicationDenied("Ambiguous approved node")
        approved_nodes[node["id"]] = (node["type"], node["name"])

    rows = {row.receipt_id: row for row in receipts}
    if len(rows) != len(receipts) or any(
        (row.task_id, row.run_id, row.lease_epoch) != (base.task_id, base.run_id, base.lease_epoch)
        or not isinstance(row.payload, dict) or row.kind not in {"release", "page_confirmation", "coverage"}
        for row in rows.values()
    ):
        raise ImpactPublicationDenied("Invalid impact receipt identity")

    material_body = _bytes(material.model_dump(mode="json"))
    material_sources = frozenset(binding.capa.sources)
    material_released = target_released = False
    seen_sources: set[ImpactSourceRef] = set()
    candidate_nodes: set[str] = set()
    plans: dict[str, tuple[str, dict[str, ImpactPage]]] = {}
    planned_releases: dict[UUID, tuple[str, ImpactPage]] = {}
    for row in (row for row in receipts if row.kind == "release"):
        scope_ref = row.payload.get("scope_ref")
        if not isinstance(scope_ref, str):
            raise ImpactPublicationDenied("Invalid release scope")
        scope = _scope(current, scope_ref)
        if (not _same_scope(row, scope) or row.payload.get("binding_digest") != base.binding_digest
                or row.payload.get("snapshot_digest") != base.snapshot_digest):
            raise ImpactPublicationDenied("Invalid release binding")
        refs = _refs(row)
        if row.payload.get("module") == "capa":
            if scope != base or row.page_key is not None or not _release_matches(
                row, material_body, (), material_sources,
            ):
                raise ImpactPublicationDenied("Formal CAPA projection unavailable")
            material_released = True
        elif row.payload.get("module") == "fmea":
            target_released = True
            if row.page_key is None:
                candidate_nodes.update(_search_nodes(current, row, refs, target, approved_nodes))
            else:
                if scope_ref not in plans:
                    step = read_step_handle(_scope(current, "directory"), scope_ref)
                    plans[scope_ref] = step, {page.key: page for page in _step_plan(current, scope_ref)}
                _, pages = plans[scope_ref]
                page = pages.get(row.page_key)
                if page is None:
                    raise ImpactPublicationDenied("Invalid canonical page")
                node_ids = {
                    node for e in page.elements for node in (e.node_id, e.source_id, e.target_id)
                    if node is not None
                }
                expected = frozenset((target, *(target_source(binding, node) for node in node_ids)))
                if not _release_matches(row, page.projection_bytes(),
                                        (e.accounting_key for e in page.elements), expected):
                    raise ImpactPublicationDenied("Invalid canonical page")
                planned_releases[row.receipt_id] = (scope_ref, page)
        else:
            raise ImpactPublicationDenied("Unknown release module")
        seen_sources.update(refs)

    if not material_released or seen_sources != sources or len({ref.source_id for ref in sources}) != len(sources):
        raise ImpactPublicationDenied("Incomplete impact source ledger")

    confirmations = defaultdict(dict)
    for row in (row for row in receipts if row.kind == "page_confirmation"):
        release_id = UUID(row.payload["release_ref"])
        scope_ref, page = planned_releases[release_id]
        if (
            not _same_scope(row, _scope(current, scope_ref)) or row.page_key != page.key
            or row.payload.get("payload_digest") != rows[release_id].payload["payload_digest"]
            or page.key in confirmations[scope_ref]
        ):
            raise ImpactPublicationDenied("Invalid canonical page confirmation")
        confirmations[scope_ref][page.key] = row.receipt_id

    step_evidence = {
        scope_ref: _merge_pages(plans[scope_ref][0], (plans[scope_ref][1][key] for key in keys))
        for scope_ref, keys in confirmations.items()
    }
    coverage = {}
    for row in (row for row in receipts if row.kind == "coverage"):
        scope_ref = row.payload["scope_ref"]
        keys = confirmations[scope_ref]
        expected = plans[scope_ref][1]
        if (
            row.page_key is not None or not _same_scope(row, _scope(current, scope_ref))
            or row.payload.get("binding_digest") != base.binding_digest
            or row.payload.get("snapshot_digest") != base.snapshot_digest
            or keys.keys() != expected.keys()
            or row.payload.get("confirmed_page_refs") != [str(keys[key]) for key in sorted(keys)]
            or scope_ref in coverage.values()
        ):
            raise ImpactPublicationDenied("Incomplete canonical coverage")
        coverage[str(row.receipt_id)] = scope_ref

    material_by_id = {ref.source_id: ref for ref in material_sources}
    by_measure = {}
    anchors = {}
    for measure in material.measures:
        key = measure.key.measure_id, measure.key.formal_revision
        if key in by_measure or not measure.source_ids or not set(measure.source_ids) <= material_by_id.keys():
            raise ImpactPublicationDenied("Invalid formal CAPA measure sources")
        by_measure[key] = frozenset(map(str, measure.source_ids))
        anchors[key] = frozenset(
            ref.node_id for ref in (material_by_id[ref_id] for ref_id in measure.source_ids)
            if ref.module == "fmea" and ref.object_id == target.object_id and ref.node_id is not None
        )
    if set(by_measure) != {(item.measure_id, item.formal_revision) for item in binding.capa.measures}:
        raise ImpactPublicationDenied("Invalid formal CAPA measure coverage")

    evidence_nodes = candidate_nodes | {node for step in step_evidence.values() for node in step.kinds}
    return _EvidenceVerifier(
        by_measure, str(target.source_id) if target_released else None,
        {str(target_source(binding, node).source_id): node for node in evidence_nodes},
        step_evidence, coverage, anchors,
    )


def build_evidence_verifier(
    current: ImpactRuntime, receipts: tuple, sources: frozenset[ImpactSourceRef],
) -> _EvidenceVerifier:
    """Rebuild every positive path and coverage receipt from authenticated runtime facts."""
    try:
        return _build(current, receipts, sources)
    except (KeyError, TypeError, ValueError) as exc:
        raise ImpactPublicationDenied("Invalid impact evidence") from exc


async def authorize_runtime_publication(
    _db, context: PublicationContext, *, current: ImpactRuntime,
) -> PublicationAuthorization:
    """Use a freshly locked runtime from lock_runtime in the same transaction."""
    scope, task, run = context.scope, context.task, context.run
    if (
        (current.task.task_id, current.run.run_id, current.epoch, current.binding_digest)
        != (scope.task_id, scope.run_id, scope.lease_epoch, scope.binding_digest)
        or (task.task_id, run.run_id) != (scope.task_id, scope.run_id)
        or context.installation.installation_id != scope.installation_id
        or current.binding != context.binding
        or validate_run_lifecycle(task, run, current.epoch, terminal_replay=True) != context.replay
    ):
        raise ImpactPublicationDenied("Impact runtime context mismatch")
    verifier = build_evidence_verifier(current, context.receipts, context.sources)
    expected = tuple((item.measure_id, item.formal_revision) for item in context.binding.capa.measures)
    return PublicationAuthorization(expected, verifier)
