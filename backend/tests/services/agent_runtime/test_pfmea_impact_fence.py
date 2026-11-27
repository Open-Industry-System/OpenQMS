from dataclasses import asdict, replace
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.schemas.pfmea_impact import ImpactSourceRef
from app.services.agent_runtime.pfmea_impact_ledger import make_release_payload, scope_digest
from app.services.agent_runtime.pfmea_impact_projections import _bytes, _scope, _step_plan, step_handle
from app.services.agent_runtime.pfmea_impact_runtime import target_source
from app.services.fmea_impact_projection import ApprovedImpactSnapshot, ImpactElement, canonical_page_digests


def _uuid(number):
    return UUID(int=number)


@pytest.fixture
def scenario():
    fmea_id, snapshot_id, factory_id = _uuid(1), _uuid(2), _uuid(3)
    first, second = _uuid(4), _uuid(5)
    common = dict(factory_id=factory_id, product_line_code="line", version="root")
    capa_first = ImpactSourceRef(
        source_id=_uuid(6), module="fmea", object_id=fmea_id, node_id="cause",
        projection_id="fmea.failure_cause.reference.v1", **common,
    )
    capa_second = ImpactSourceRef(
        source_id=_uuid(7), module="capa", object_id=_uuid(9),
        projection_id="capa.d2.snapshot.v1", **common,
    )
    measures = (
        SimpleNamespace(key=SimpleNamespace(measure_id=first, formal_revision=None), source_ids=(capa_first.source_id,)),
        SimpleNamespace(key=SimpleNamespace(measure_id=second, formal_revision=None), source_ids=(capa_second.source_id,)),
    )
    capa = SimpleNamespace(factory_id=factory_id, product_line_code="line",
                           sources=(capa_first, capa_second), measures=tuple(m.key for m in measures))
    approved = SimpleNamespace(approved_version_id=snapshot_id, fmea_id=fmea_id, snapshot_hash="a" * 64, major_no=3)
    binding = SimpleNamespace(capa=capa, target=approved)
    material = SimpleNamespace(
        binding=capa, measures=measures, model_dump=lambda **_: {"root": "employee verification"},
    )
    graph = {
        "nodes": [
            {"id": node, "type": kind, "name": node}
            for node, kind in (("step", "ProcessStep"), ("mode", "FailureMode"),
                               ("cause", "FailureCause"), ("control", "PreventionControl"))
        ],
        "edges": [
            {"source": "step", "target": "mode", "type": "HAS_FAILURE_MODE"},
            {"source": "cause", "target": "mode", "type": "CAUSE_OF"},
            {"source": "cause", "target": "control", "type": "PREVENTED_BY"},
        ],
    }
    current = SimpleNamespace(
        task=SimpleNamespace(task_id=_uuid(10)), run=SimpleNamespace(run_id=_uuid(11)),
        binding=binding, binding_digest="b" * 64, epoch=3, material=material,
        snapshot=ApprovedImpactSnapshot(snapshot_id, 3, approved.snapshot_hash, graph),
    )
    scope_ref = step_handle(_scope(current, "directory"), "step")
    scope = _scope(current, scope_ref)
    page, = _step_plan(current, scope_ref)
    expected = canonical_page_digests((page,))

    def receipt(number, kind, receipt_scope, payload, page_key=None):
        return SimpleNamespace(
            receipt_id=_uuid(number), kind=kind, task_id=scope.task_id, run_id=scope.run_id,
            lease_epoch=scope.lease_epoch, scope_digest=scope_digest(receipt_scope),
            page_key=page_key, payload=payload,
        )

    material_scope = _scope(current, "capa.material")
    material_release = receipt(20, "release", material_scope, make_release_payload(
        material_scope, module="capa", body=_bytes(material.model_dump(mode="json")), element_keys=(), sources=capa.sources,
    ))
    nodes = {node["id"]: target_source(binding, node["id"]) for node in graph["nodes"]}
    sources = [target_source(binding), *nodes.values()]
    released = receipt(21, "release", scope, make_release_payload(
        scope, module="fmea", body=page.projection_bytes(), element_keys=(e.accounting_key for e in page.elements),
        sources=sources, page_key=page.key, expected_page_digests=expected,
    ), page.key)
    ack = receipt(22, "page_confirmation", scope, {
        "release_ref": str(released.receipt_id), "payload_digest": expected[page.key],
    }, page.key)
    coverage = receipt(23, "coverage", scope, {
        "confirmed_page_refs": [str(ack.receipt_id)], "binding_digest": current.binding_digest,
        "snapshot_digest": approved.snapshot_hash, "scope_ref": scope_ref,
    })

    return SimpleNamespace(
        current=current, first=(first, None), second=(second, None), nodes=nodes, scope=scope,
        material_ref=str(capa_first.source_id), other_material_ref=str(capa_second.source_id),
        receipts=[material_release, released, ack, coverage], coverage_ref=str(coverage.receipt_id),
        sources=frozenset((*capa.sources, *sources)), receipt=receipt,
    )


def _verifier(scenario):
    from app.services.agent_runtime.pfmea_impact_fence import build_evidence_verifier

    return build_evidence_verifier(scenario.current, tuple(scenario.receipts), scenario.sources)


def test_only_capa_source_of_exact_measure_can_link_released_graph_path(scenario):
    s = scenario
    v = _verifier(s)
    targets = tuple(str(node.source_id) for node in s.nodes.values())
    assert v.verify_evidence(s.first, (s.material_ref, *targets))
    assert not v.verify_evidence(s.first, (s.other_material_ref, *targets))
    assert not v.verify_evidence((s.first[0], _uuid(222)), (s.material_ref,))
    control = str(s.nodes["control"].source_id)
    assert v.verify_impact_path(s.first, control, (s.material_ref, *targets))
    assert not v.verify_impact_path(s.first, control, targets)
    assert not v.verify_impact_path(
        s.first, control, (s.material_ref, *[target for target in targets if target != str(s.nodes["cause"].source_id)]),
    )


def test_coverage_chain_required_and_never_stands_in_for_formal_exclusion(scenario):
    s = scenario
    v = _verifier(s)
    assert v.verify_coverage(s.first, (s.coverage_ref,))
    assert not v.verify_coverage(s.second, (s.coverage_ref,))
    assert not v.verify_exclusion(s.first, (s.material_ref,), (s.coverage_ref,))
    with pytest.raises(PermissionError):
        s.receipts.pop(2)
        _verifier(s)


@pytest.mark.parametrize("change", ["digest", "unreleased_node", "wrong_scope", "wrong_run"])
def test_canonical_page_receipt_cannot_be_rebound_or_expand_released_sources(scenario, change):
    s = scenario
    release = s.receipts[1]
    if change == "digest":
        release.payload["payload_digest"] = sha256(b"other bytes").hexdigest()
    elif change == "unreleased_node":
        extra = target_source(s.current.binding, "unreleased")
        release.payload["sources"].append(extra.model_dump(mode="json"))
        s.sources |= {extra}
    elif change == "wrong_scope":
        release.scope_digest = scope_digest(replace(s.scope, scope_ref="other scope"))
    else:
        release.run_id = _uuid(100)
    with pytest.raises(PermissionError):
        _verifier(s)


def test_possible_release_preserves_sources_but_does_not_prove_path_without_confirmed_page(scenario):
    s = scenario
    s.receipts = s.receipts[:2]
    v = _verifier(s)
    target = str(s.nodes["control"].source_id)
    assert not v.verify_impact_path(s.first, target, (s.material_ref, target))
    assert not v.verify_evidence(s.first, (target,))
    assert not v.verify_coverage(s.first, (s.coverage_ref,))


def test_released_search_candidate_is_citable_but_never_an_adjustment_path(scenario):
    s = scenario
    target = target_source(s.current.binding)
    step = s.nodes["step"]
    search_scope = _scope(s.current, "search:" + sha256(b"step").hexdigest())
    element = ImpactElement(kind="ProcessStep", node_id="step", name="step")
    candidate = {**asdict(element), "source_id": str(step.source_id),
                 "scope_ref": step_handle(_scope(s.current, "directory"), "step")}
    search = s.receipt(25, "release", search_scope, make_release_payload(
        search_scope, module="fmea", body=_bytes({"candidates": [candidate], "truncated": False}),
        element_keys=(element.accounting_key,), sources=(target, step),
    ))
    s.receipts = [s.receipts[0], search]
    s.sources = frozenset((*s.current.binding.capa.sources, target, step))
    v = _verifier(s)
    step_ref = str(step.source_id)
    assert v.verify_evidence(s.first, (s.material_ref, step_ref))
    assert not v.verify_impact_path(s.first, step_ref, (s.material_ref, step_ref))
    assert not v.verify_evidence(s.first, (str(s.nodes["cause"].source_id),))
    search.payload["payload_digest"] = sha256(b"{}").hexdigest()
    with pytest.raises(PermissionError):
        _verifier(s)
