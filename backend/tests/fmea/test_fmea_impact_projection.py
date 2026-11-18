import pytest


def _snapshot():
    nodes = [
        ("step", "ProcessStep", "OP40 tightening"),
        ("element", "ProcessWorkElement", "Controller"),
        ("fn", "ProcessWorkElementFunction", "Load order program"),
        ("mode", "FailureMode", "Torque low"),
        ("effect", "FailureEffect", "Joint loosens"),
        ("cause-a", "FailureCause", "Wrong torque program"),
        ("cause-b", "FailureCause", "Retained previous recipe"),
        ("control-a", "PreventionControl", "Verify program"),
        ("control-b", "DetectionControl", "Verify last sample"),
    ]
    edges = [
        ("step", "element", "HAS_WORK_ELEMENT"),
        ("element", "fn", "HAS_FUNCTION"),
        ("fn", "mode", "HAS_FAILURE_MODE"),
        ("mode", "effect", "EFFECT_OF"),
        ("cause-a", "mode", "CAUSE_OF"),
        ("cause-b", "mode", "CAUSE_OF"),
        ("cause-a", "control-a", "PREVENTED_BY"),
        ("mode", "control-b", "DETECTED_BY"),
    ]
    return {
        "nodes": [{"id": i, "type": t, "name": n, "private_note": "omit"} for i, t, n in nodes],
        "edges": [{"source": a, "target": b, "type": t} for a, b, t in edges],
    }


def test_full_chain_keeps_differently_named_causes_and_control_ownership():
    from app.services.fmea_impact_projection import plan_step_coverage

    graph = _snapshot()
    pages = plan_step_coverage(graph, step_id="step", snapshot_digest="version-a", page_size=4)
    entries = [entry for page in pages for entry in page.elements]
    assert {e.node_id for e in entries if e.kind == "FailureCause"} == {"cause-a", "cause-b"}
    assert {e.node_id for e in entries if e.kind in {"PreventionControl", "DetectionControl"}} == {
        "control-a", "control-b",
    }
    assert {(e.source_id, e.target_id) for e in entries if e.kind == "DETECTED_BY"} == {
        ("mode", "control-b"),
    }
    assert ("mode", "effect") in {(e.source_id, e.target_id) for e in entries if e.kind == "EFFECT_OF"}
    assert all(0 < len(page.elements) <= 4 for page in pages)
    assert "private_note" not in repr(entries)
    assert len({element.accounting_key for element in entries}) == len(entries)
    graph["nodes"].reverse()
    graph["edges"].reverse()
    assert pages == plan_step_coverage(graph, step_id="step", snapshot_digest="version-a", page_size=4)


def test_duplicate_or_foreign_confirmation_cannot_replace_a_missing_page():
    from app.services.fmea_impact_projection import coverage_complete, plan_step_coverage

    pages = plan_step_coverage(_snapshot(), step_id="step", snapshot_digest="version-a", page_size=4)
    foreign = plan_step_coverage(_snapshot(), step_id="step", snapshot_digest="version-b", page_size=4)
    keys = [p.key for p in pages]
    assert len(keys) > 1
    assert not coverage_complete(pages, keys[:-1] + [keys[0]])
    assert not coverage_complete(pages, keys[:-1] + [foreign[-1].key])
    assert not coverage_complete(pages, keys + [foreign[-1].key])
    assert coverage_complete(pages, keys + [keys[0]])


@pytest.mark.parametrize("fault", [
    "dangling", "duplicate_node", "wrong_kind", "no_chain", "unowned_mode",
    "unowned_control", "unowned_effect",
])
def test_incomplete_or_ambiguous_graph_cannot_yield_a_coverage_plan(fault):
    from app.services.fmea_impact_projection import IncompleteImpactScope, plan_step_coverage

    graph = _snapshot()
    if fault == "dangling":
        graph["edges"][-1]["target"] = "missing"
    elif fault == "duplicate_node":
        graph["nodes"].append(graph["nodes"][0].copy())
    elif fault == "wrong_kind":
        graph["nodes"][-1]["type"] = "FailureEffect"
    elif fault == "no_chain":
        graph["edges"] = []
    elif fault == "unowned_mode":
        graph["nodes"].append({"id": "unowned", "type": "FailureMode", "name": "Unmapped mode"})
    else:
        removed = "DETECTED_BY" if fault == "unowned_control" else "EFFECT_OF"
        graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != removed]
    with pytest.raises(IncompleteImpactScope):
        plan_step_coverage(graph, step_id="step", snapshot_digest="version-a")


def test_exact_step_reference_required_for_a_coverage_plan():
    from app.services.fmea_impact_projection import IncompleteImpactScope, plan_step_coverage

    with pytest.raises(IncompleteImpactScope):
        plan_step_coverage(_snapshot(), step_id="OP40 tightening", snapshot_digest="version-a")


@pytest.mark.parametrize("limit", ["elements", "pages", "bytes"])
def test_over_budget_scope_cannot_be_mistaken_for_complete_coverage(limit):
    from app.services.fmea_impact_projection import IncompleteImpactScope, plan_step_coverage

    graph = _snapshot()
    page_size = 25
    if limit == "elements":
        for i in range(110):
            cause_id = f"cause-extra-{i}"
            graph["nodes"].append({"id": cause_id, "type": "FailureCause", "name": "Additional cause"})
            graph["edges"].append({"source": cause_id, "target": "mode", "type": "CAUSE_OF"})
    elif limit == "pages":
        page_size = 1
        graph["nodes"].append({"id": "cause-extra", "type": "FailureCause", "name": "Additional cause"})
        graph["edges"].append({"source": "cause-extra", "target": "mode", "type": "CAUSE_OF"})
    else:
        graph["nodes"][0]["name"] = "工" * 100_000
    with pytest.raises(IncompleteImpactScope, match="budget"):
        plan_step_coverage(graph, step_id="step", snapshot_digest="version-a", page_size=page_size)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_read_uses_latest_approved_snapshot_and_keeps_draft_out(db, default_factory, admin_user):
    from copy import deepcopy
    from uuid import uuid4

    from sqlalchemy import delete

    from app.models.audit import AuditLog
    from app.models.fmea import FMEADocument
    from app.services import version_service
    from app.services.fmea_impact_projection import ImpactTargetUnavailable, read_approved_snapshot
    from tests.conftest import _scope_for

    graph = _snapshot()
    product_line = "DC-DC-100"
    fmea = FMEADocument(
        document_no=f"R7-{uuid4().hex[:12]}", title="Tightening",
        factory_id=default_factory.id, created_by=admin_user.user_id,
        product_line_code=product_line, fmea_type="PFMEA", status="in_review",
        graph_data=graph,
    )
    db.add(fmea)
    await db.flush()
    fmea_id, actor_id = fmea.fmea_id, admin_user.user_id
    approval = await version_service._create_fmea_version_no_commit(db, fmea, "approve", None, actor_id)
    approval_id = approval.version_id
    draft = deepcopy(graph)
    draft["nodes"][0]["name"] = "Draft only"
    fmea.graph_data = draft
    await db.flush()
    submit = await version_service._create_fmea_version_no_commit(db, fmea, "submit", None, actor_id)
    scope = _scope_for(admin_user, default_factory)
    coordinates = dict(factory_id=default_factory.id, product_line_code=product_line)

    selected = await read_approved_snapshot(db, scope, fmea_id, **coordinates)
    assert selected.version_id == approval_id
    assert selected.graph["nodes"][0]["name"] == graph["nodes"][0]["name"]
    with pytest.raises(ImpactTargetUnavailable):
        await read_approved_snapshot(db, scope, fmea_id, expected_version_id=submit.version_id, **coordinates)
    with pytest.raises(ImpactTargetUnavailable):
        await read_approved_snapshot(db, scope, fmea_id, **{**coordinates, "product_line_code": "OTHER"})
    with pytest.raises(ImpactTargetUnavailable):
        await read_approved_snapshot(db, scope, fmea_id, **{**coordinates, "factory_id": uuid4()})

    fmea.product_line_code = "OTHER"
    await db.flush()
    with pytest.raises(ImpactTargetUnavailable):
        await read_approved_snapshot(db, scope, fmea_id, **{**coordinates, "product_line_code": "OTHER"})
    fmea.product_line_code = product_line
    await db.flush()
    new_approval = await version_service._create_fmea_version_no_commit(db, fmea, "approve", None, actor_id)
    with pytest.raises(ImpactTargetUnavailable):
        await read_approved_snapshot(db, scope, fmea_id, expected_version_id=approval_id, **coordinates)
    selected = await read_approved_snapshot(db, scope, fmea_id, **coordinates)
    assert selected.version_id == new_approval.version_id
    assert selected.graph["nodes"][0]["name"] == "Draft only"

    # An older approval without captured scope may not inherit the live line.
    await db.execute(delete(AuditLog).where(
        AuditLog.table_name == "fmea_versions", AuditLog.record_id == new_approval.version_id,
    ))
    with pytest.raises(ImpactTargetUnavailable):
        await read_approved_snapshot(db, scope, fmea_id, **coordinates)

    fmea.fmea_type = "DFMEA"
    await db.flush()
    with pytest.raises(ImpactTargetUnavailable):
        await read_approved_snapshot(db, scope, fmea_id, **coordinates)


def test_coverage_check_uses_server_serialized_page_not_the_acknowledgement_bytes():
    import json
    from uuid import uuid4

    from app.services.agent_runtime.pfmea_impact_release import (
        PageConfirmationMismatch, PageRelease, PageScope, confirm_page,
        confirmed_page_keys, verify_page_payload,
    )
    from app.services.fmea_impact_projection import (
        canonical_page_digests, coverage_complete, plan_step_coverage,
    )

    pages = plan_step_coverage(_snapshot(), step_id="step", snapshot_digest="version-a", page_size=4)
    scope = PageScope(uuid4(), uuid4(), 0, "binding-a", "version-a", "step")
    expected = canonical_page_digests(pages)
    acknowledgements = []
    for page in pages:
        payload = page.projection_bytes()
        assert json.loads(payload)["page_key"] == page.key
        digest = verify_page_payload(page.key, payload, expected_page_digests=expected)
        release = PageRelease(uuid4(), scope, page.key, digest)
        acknowledgements.append(confirm_page(release, scope=scope, release_ref=release.release_ref,
            page_key=page.key, payload_digest=digest))
    assert coverage_complete(pages, confirmed_page_keys(scope, acknowledgements,
        expected_page_digests=expected))
    with pytest.raises(PageConfirmationMismatch):
        verify_page_payload(pages[0].key, pages[1].projection_bytes(), expected_page_digests=expected)


def test_step_discovery_paginates_distinct_candidates_without_proving_coverage():
    from app.services.fmea_impact_projection import discover_snapshot_steps, plan_step_coverage

    graph = _snapshot()
    graph["nodes"].append({"id": "step-2", "type": "ProcessStep", "name": "OP41 tightening"})
    graph["nodes"].append({"id": "action", "type": "RecommendedAction", "name": "tightening"})
    first = discover_snapshot_steps(graph, term="TIGHTENING", page_size=1)
    assert [(e.node_id, e.kind) for e in first.elements] == [("step", "ProcessStep")]
    assert first.next_offset == 1
    last = discover_snapshot_steps(graph, term="tightening", offset=first.next_offset, page_size=1)
    assert [e.node_id for e in last.elements] == ["step-2"]
    assert last.next_offset is None
    full = plan_step_coverage(graph, step_id="step", snapshot_digest="approved")
    assert {element.kind for page in full for element in page.elements} >= {
        "FailureMode", "FailureCause", "PreventionControl", "DetectionControl",
    }


def test_discovery_rejects_duplicate_id_even_if_the_other_node_is_not_a_step():
    from app.services.fmea_impact_projection import IncompleteImpactScope, discover_snapshot_steps

    graph = _snapshot()
    graph["nodes"].append({"id": "step", "type": "RecommendedAction", "name": "Unrelated"})
    with pytest.raises(IncompleteImpactScope):
        discover_snapshot_steps(graph, term="Tightening")
