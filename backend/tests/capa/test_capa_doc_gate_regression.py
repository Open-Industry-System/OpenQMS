"""Regression tests for 终审第七轮 findings (US-E2E-01.7).

Covers the four paths the reviewer called out as untested:
1. regenerate (P0#1) — same CAPA can generate twice; old row is demoted
2. wrong-field update does not count as coverage (P0#2)
3. no-baseline new document does not crash _compute_input_hash (P0#3)
4. CP modify/delete coverage uses item_id + field (P1#4)
Plus empty-list LLM → done → confirm_no_affected (P1#5).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select, text

from app.models.audit import AuditLog
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
from app.services import capa_doc_gate_service
from app.services.capa_doc_gate_service import (
    _build_allowlist,
    _compute_input_hash,
    _match_key_point,
    _validate_and_backfill,
    _validate_key_point,
)


# ---------------------------------------------------------------------------
# P0#1: regenerate does not hit UNIQUE(capa_id, factory_id)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_succeeds_without_unique_violation(db, capa_d8_gate_with_docs, docg_llm_mock):
    """Same CAPA can generate twice. Old row is demoted (is_current=false); new is current."""
    capa, user = capa_d8_gate_with_docs
    docg_llm_mock.return_value = {
        "affected_docs": [
            {
                "doc_id": str(capa.fmea_ref_id),
                "key_points": [
                    {
                        "target_kind": "fmea_node",
                        "expected_action": "modify",
                        "field": "prevention_control",
                        "target_key": "node-1",
                    }
                ],
                "update_suggestion": "建议更新预防控制",
            }
        ]
    }
    r1 = await capa_doc_gate_service.generate_impact_analysis(db, capa, user.user_id)
    assert r1["status"] == "done"
    r2 = await capa_doc_gate_service.generate_impact_analysis(db, capa, user.user_id)
    assert r2["status"] == "done"
    # Exactly one is_current
    currents = (await db.execute(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.is_current == True
        )
    )).scalars().all()
    assert len(currents) == 1
    assert str(currents[0].analysis_id) == r2["analysis_id"]
    # Old row still present (history retained)
    all_rows = (await db.execute(
        select(CapaDocgAnalysis).where(CapaDocgAnalysis.capa_id == capa.report_id)
    )).scalars().all()
    assert len(all_rows) == 2
    demoted = [r for r in all_rows if not r.is_current]
    assert len(demoted) == 1
    assert demoted[0].status == "done"  # demoted, not deleted


# ---------------------------------------------------------------------------
# P0#2: field-level coverage — wrong field does not cover
# ---------------------------------------------------------------------------


def test_match_key_point_requires_field_in_changes():
    """modify requires the requested field to appear in the diff changes, not just node identity."""
    # Diff has node-1 modified on description (wrong field)
    diff = {
        "modified_nodes": [
            {"node_id": "node-1", "changes": [{"field": "description", "old": "a", "new": "b"}], "impact_chain": []}
        ],
        "added_nodes": [],
        "deleted_nodes": [],
    }
    kp = {"expected_action": "modify", "target_kind": "fmea_node",
          "field": "prevention_control", "target_key": "node-1"}
    assert _match_key_point(kp, diff, latest=None, doc_type="fmea") is False

    # Same node, correct field → covered
    diff["modified_nodes"][0]["changes"] = [{"field": "prevention_control", "old": "a", "new": "b"}]
    assert _match_key_point(kp, diff, latest=None, doc_type="fmea") is True


def test_validate_key_point_rejects_field_outside_allowlist():
    """modify with a field not in existing_targets.allowed_fields → validation error."""
    cand = {
        "doc_type": "fmea",
        "existing_targets": [
            {"target_kind": "fmea_node", "target_key": "node-1",
             "allowed_fields": ["prevention_control", "detection_control", "name"]}
        ],
        "add_anchors": [],
        "baseline_version": {"major": 1, "minor": 0, "sha256": "x"},
    }
    kp = {"expected_action": "modify", "target_kind": "fmea_node",
          "field": "description", "target_key": "node-1"}
    err = _validate_key_point(kp, cand)
    assert err is not None
    assert "field" in err


def test_validate_key_point_rejects_unknown_target_key():
    """modify of a target_key not in existing_targets → validation error."""
    cand = {
        "doc_type": "fmea",
        "existing_targets": [
            {"target_kind": "fmea_node", "target_key": "node-1",
             "allowed_fields": ["prevention_control"]}
        ],
        "add_anchors": [],
        "baseline_version": {"major": 1, "minor": 0, "sha256": "x"},
    }
    kp = {"expected_action": "modify", "target_kind": "fmea_node",
          "field": "prevention_control", "target_key": "node-unknown"}
    err = _validate_key_point(kp, cand)
    assert err is not None
    assert "target_key" in err


# ---------------------------------------------------------------------------
# P0#3: no-baseline new document does not crash _compute_input_hash
# ---------------------------------------------------------------------------


def test_compute_input_hash_handles_none_baseline():
    """baseline_version=None (new document after CAPA) must not AttributeError."""
    class FakeCapa:
        factory_id = uuid.uuid4()
        product_line_code = "DC-DC-100"
        d4_root_cause = "rc"
        d5_correction = "c"
        d7_prevention = "p"
        severity = "serious"
        fmea_ref_id = None
        fmea_node_id = None

    candidates = [
        {"doc_type": "fmea", "doc_id": str(uuid.uuid4()),
         "baseline_version_id": None, "baseline_version": None},
        {"doc_type": "control_plan", "doc_id": str(uuid.uuid4()),
         "baseline_version_id": None, "baseline_version": None},
    ]
    h = _compute_input_hash(FakeCapa(), candidates)
    assert isinstance(h, str) and len(h) == 64


# ---------------------------------------------------------------------------
# P1#4: CP modify matches on item_id + field (not source_fmea_node_id alone)
# ---------------------------------------------------------------------------


def test_cp_item_id_primary_modify_product_char_stays_modify():
    """Changing product_characteristic must be modify (not delete+add) when item_id stable."""
    from app.services.capa_doc_gate_service import _diff_cp_items_for_gate, _match_key_point
    v1 = [{"item_id": "iid-1", "source_fmea_node_id": "step-1",
           "product_characteristic": "A", "process_characteristic": "", "control_method": "X"}]
    v2 = [{"item_id": "iid-1", "source_fmea_node_id": "step-1",
           "product_characteristic": "B", "process_characteristic": "", "control_method": "X"}]
    d = _diff_cp_items_for_gate(v1, v2)
    assert d["deleted_items"] == []
    assert d["added_items"] == []
    assert len(d["modified_items"]) == 1
    assert any(c["field"] == "product_characteristic" for c in d["modified_items"][0]["changes"])
    kp = {"expected_action": "modify", "target_kind": "cp_item",
          "field": "product_characteristic", "target_key": "iid-1"}
    assert _match_key_point(kp, {"items": d}, latest=None, doc_type="control_plan") is True
    # must NOT be covered as delete
    kp_del = {"expected_action": "delete", "target_kind": "cp_item",
              "field": "control_method", "target_key": "iid-1"}
    assert _match_key_point(kp_del, {"items": d}, latest=None, doc_type="control_plan") is False


def test_cp_full_rebuild_same_content_is_delete_and_add_not_modify():
    """Delete-all + recreate with same fingerprint must NOT be modify (no heuristic remap)."""
    from app.services.capa_doc_gate_service import _diff_cp_items_for_gate, _match_key_point
    v1 = [{"item_id": "old-id", "source_fmea_node_id": "node-5",
           "product_characteristic": "char-a", "process_characteristic": "",
           "control_method": "A"}]
    v2 = [{"item_id": "new-id", "source_fmea_node_id": "node-5",
           "product_characteristic": "char-a", "process_characteristic": "",
           "control_method": "B"}]
    d = _diff_cp_items_for_gate(v1, v2)
    assert len(d["deleted_items"]) == 1
    assert len(d["added_items"]) == 1
    assert d["modified_items"] == []
    kp = {"expected_action": "modify", "target_kind": "cp_item",
          "field": "control_method", "target_key": "old-id"}
    assert _match_key_point(kp, {"items": d}, latest=None, doc_type="control_plan") is False
    kp_del = {"expected_action": "delete", "target_kind": "cp_item",
              "field": "control_method", "target_key": "old-id"}
    assert _match_key_point(kp_del, {"items": d}, latest=None, doc_type="control_plan") is True


def test_cp_full_rebuild_two_rows_unique_fp_still_delete_and_add():
    """Zero shared ids + unique fingerprints is STILL delete+add (no legacy remap at all)."""
    from app.services.capa_doc_gate_service import _diff_cp_items_for_gate
    v1 = [
        {"item_id": "old-a", "source_fmea_node_id": "s1",
         "product_characteristic": "pa", "process_characteristic": "", "control_method": "A"},
        {"item_id": "old-b", "source_fmea_node_id": "s2",
         "product_characteristic": "pb", "process_characteristic": "", "control_method": "B"},
    ]
    v2 = [
        {"item_id": "new-a", "source_fmea_node_id": "s1",
         "product_characteristic": "pa", "process_characteristic": "", "control_method": "A2"},
        {"item_id": "new-b", "source_fmea_node_id": "s2",
         "product_characteristic": "pb", "process_characteristic": "", "control_method": "B"},
    ]
    d = _diff_cp_items_for_gate(v1, v2)
    assert len(d["deleted_items"]) == 2
    assert len(d["added_items"]) == 2
    assert d["modified_items"] == []


def test_cp_sibling_empty_fingerprint_pure_delete_and_add():
    """Empty fingerprints under full rebuild = pure delete+add (no remap)."""
    from app.services.capa_doc_gate_service import _diff_cp_items_for_gate
    a = {"item_id": "ia", "source_fmea_node_id": "step-1",
         "product_characteristic": "", "process_characteristic": "", "control_method": "A"}
    b = {"item_id": "ib", "source_fmea_node_id": "step-1",
         "product_characteristic": "", "process_characteristic": "", "control_method": "B"}
    a2 = {"item_id": "ia2", "source_fmea_node_id": "step-1",
          "product_characteristic": "", "process_characteristic": "", "control_method": "A"}
    b2 = {"item_id": "ib2", "source_fmea_node_id": "step-1",
          "product_characteristic": "", "process_characteristic": "", "control_method": "B"}
    d = _diff_cp_items_for_gate([a, b], [a2, b2])
    assert len(d["deleted_items"]) == 2
    assert len(d["added_items"]) == 2
    assert d["modified_items"] == []


def test_cp_sibling_items_same_source_delete_one():
    """Two items under same source with distinct product_char: deleting one works via item_id."""
    from app.services.capa_doc_gate_service import _diff_cp_items_for_gate, _match_key_point
    a = {"item_id": "ia", "source_fmea_node_id": "step-1",
         "product_characteristic": "char-a", "process_characteristic": "", "control_method": "A"}
    b = {"item_id": "ib", "source_fmea_node_id": "step-1",
         "product_characteristic": "char-b", "process_characteristic": "", "control_method": "B"}
    d = _diff_cp_items_for_gate([a, b], [b])
    assert len(d["deleted_items"]) == 1
    assert d["deleted_items"][0]["item_id"] == "ia"
    kp = {"expected_action": "delete", "target_kind": "cp_item",
          "field": "control_method", "target_key": "ia"}
    assert _match_key_point(kp, {"items": d}, latest=None, doc_type="control_plan") is True


@pytest.mark.asyncio
async def test_record_gate_waiver_inserts_passed_decision_with_reason(db, capa_with_done_analysis_no_bump):
    """Waiver forces passed decision + waiver_reason + DOC_GATE_WAIVER audit."""
    from app.models.capa_doc_gate import CapaDocgDecision
    from app.services import capa_doc_gate_service
    capa, user = capa_with_done_analysis_no_bump
    result = await capa_doc_gate_service.record_gate_waiver(
        db, capa, "lineage break accepted: delete+add intentional", user.user_id
    )
    assert result["decision"] == "passed"
    assert "lineage break" in result["waiver_reason"]
    dec = (await db.execute(
        select(CapaDocgDecision).order_by(CapaDocgDecision.revision.desc())
    )).scalars().first()
    assert dec.decision == "passed"
    assert dec.waiver_reason is not None
    assert dec.no_affected_confirmed is False
    audits = (await db.execute(select(AuditLog).where(AuditLog.action == "DOC_GATE_WAIVER"))).scalars().all()
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_record_gate_waiver_requires_reason(db, capa_with_done_analysis_no_bump):
    from app.services import capa_doc_gate_service
    capa, user = capa_with_done_analysis_no_bump
    with pytest.raises(ValueError, match="waiver reason 必填"):
        await capa_doc_gate_service.record_gate_waiver(db, capa, "  ", user.user_id)


@pytest.mark.asyncio
async def test_record_gate_waiver_requires_analysis(db, capa_d8_gate):
    """No current analysis → raise (cannot waive a non-existent gate)."""
    from app.services import capa_doc_gate_service
    capa, user = capa_d8_gate
    with pytest.raises(ValueError, match="未生成影响分析"):
        await capa_doc_gate_service.record_gate_waiver(db, capa, "r", user.user_id)


@pytest.mark.asyncio
async def test_waiver_passed_decision_unblocks_gate(db, capa_with_done_analysis_no_bump):
    """After waiver, _d8_doc_gate_gate must not raise (decision=passed)."""
    from app.services import capa_doc_gate_service, capa_service
    capa, user = capa_with_done_analysis_no_bump
    await capa_doc_gate_service.record_gate_waiver(db, capa, "accepted", user.user_id)
    # Gate should now pass C9 (no input change) + decision=passed. C8 has no
    # version_snapshot (waiver), so gate reaches the decision check and passes.
    await capa_service._d8_doc_gate_gate(db, capa)


@pytest.mark.asyncio
async def test_phase2_non_dict_llm_output_becomes_failed(db, capa_d8_gate_with_docs, docg_llm_mock):
    """Top-level non-dict LLM response must mark analysis failed, not leave running."""
    from app.models.capa_doc_gate import CapaDocgAnalysis
    from sqlalchemy import select
    capa, user = capa_d8_gate_with_docs
    docg_llm_mock.return_value = None  # non-dict top-level
    result = await capa_doc_gate_service.generate_impact_analysis(db, capa, user.user_id)
    assert result["status"] == "failed"
    rows = (await db.execute(
        select(CapaDocgAnalysis).where(CapaDocgAnalysis.capa_id == capa.report_id)
    )).scalars().all()
    assert any(r.status == "failed" for r in rows)
    assert not any(r.status == "running" for r in rows)


def test_add_requires_field_and_nonempty_value():
    """add without field fails validation; empty control_method does not cover."""
    from app.services.capa_doc_gate_service import _validate_key_point, _match_key_point
    cand = {
        "doc_type": "control_plan",
        "existing_targets": [],
        "add_anchors": [{"parent_node_id": "node-5", "node_type": "FailureMode"}],
        "baseline_version": {"major": 1, "minor": 0, "sha256": "x"},
    }
    kp_nofield = {
        "expected_action": "add", "target_kind": "cp_item",
        "add_anchor": {"parent_node_id": "node-5", "node_type": "FailureMode",
                       "business_key": "char-a"},
    }
    err = _validate_key_point(kp_nofield, cand)
    assert err is not None and "field" in err

    kp = {**kp_nofield, "field": "control_method"}
    assert _validate_key_point(kp, cand) is None

    # empty control_method on added item → not covered
    diff_empty = {
        "items": {
            "added_items": [{
                "item_id": "i1", "source_fmea_node_id": "node-5",
                "product_characteristic": "char-a", "control_method": "",
            }],
            "deleted_items": [], "modified_items": [],
        }
    }
    assert _match_key_point(kp, diff_empty, latest=None, doc_type="control_plan") is False
    # non-empty → covered
    diff_ok = {
        "items": {
            "added_items": [{
                "item_id": "i1", "source_fmea_node_id": "node-5",
                "product_characteristic": "char-a", "control_method": "SPC",
            }],
            "deleted_items": [], "modified_items": [],
        }
    }
    assert _match_key_point(kp, diff_ok, latest=None, doc_type="control_plan") is True


def test_discriminant_presence_not_truthiness():
    """Empty target_key / empty add_anchor still count as 'present' for mutual exclusion."""
    from app.services.capa_doc_gate_service import _validate_key_point
    cand = {
        "doc_type": "fmea",
        "existing_targets": [{"target_kind": "fmea_node", "target_key": "node-1",
                             "allowed_fields": ["prevention_control"]}],
        "add_anchors": [{"parent_node_id": "node-1", "node_type": "FailureMode"}],
        "baseline_version": {"major": 1, "minor": 0, "sha256": "x"},
    }
    # both keys present (even empty) → mutual exclusion error
    err = _validate_key_point(
        {"expected_action": "modify", "target_kind": "fmea_node",
         "target_key": "", "add_anchor": {}, "field": "prevention_control"},
        cand,
    )
    assert err is not None and "互斥" in err


def test_match_key_point_cp_modify_uses_item_id_and_field():
    """CP modify: target_key is item_id; field must appear in changes."""
    from app.services.capa_doc_gate_service import _match_key_point
    diff = {
        "items": {
            "modified_items": [
                {"item_id": "item-1", "source_fmea_node_id": "node-5",
                 "changes": [{"field": "control_method", "old": "a", "new": "b"}]}
            ],
            "added_items": [],
            "deleted_items": [],
        },
        "headers": [],
    }
    kp = {"expected_action": "modify", "target_kind": "cp_item",
          "field": "control_method", "target_key": "item-1"}
    assert _match_key_point(kp, diff, latest=None, doc_type="control_plan") is True
    kp_wrong = {**kp, "field": "reaction_plan"}
    assert _match_key_point(kp_wrong, diff, latest=None, doc_type="control_plan") is False
    kp_wrong_id = {**kp, "target_key": "item-x"}
    assert _match_key_point(kp_wrong_id, diff, latest=None, doc_type="control_plan") is False


def test_match_key_point_cp_delete_uses_item_id():
    """CP delete: target_key is item_id."""
    from app.services.capa_doc_gate_service import _match_key_point
    diff = {
        "items": {
            "modified_items": [],
            "added_items": [],
            "deleted_items": [{"item_id": "item-1", "source_fmea_node_id": "node-5"}],
        },
        "headers": [],
    }
    kp = {"expected_action": "delete", "target_kind": "cp_item",
          "field": "control_method", "target_key": "item-1"}
    assert _match_key_point(kp, diff, latest=None, doc_type="control_plan") is True
    kp_miss = {**kp, "target_key": "item-x"}
    assert _match_key_point(kp_miss, diff, latest=None, doc_type="control_plan") is False


def test_document_kind_rejects_non_add_and_existing_baseline():
    """document target_kind only valid for baseline=NULL + add (gate bypass fix)."""
    cand_existing = {
        "doc_type": "fmea",
        "existing_targets": [{"target_kind": "fmea_node", "target_key": "node-1",
                             "allowed_fields": ["prevention_control"]}],
        "add_anchors": [],
        "baseline_version": {"major": 1, "minor": 0, "sha256": "x"},
    }
    # document/delete on existing FMEA → reject
    err = _validate_key_point(
        {"expected_action": "delete", "target_kind": "document", "target_key": "any"},
        cand_existing,
    )
    assert err is not None
    # document/add on existing baseline → reject
    err2 = _validate_key_point(
        {"expected_action": "add", "target_kind": "document"},
        cand_existing,
    )
    assert err2 is not None and "baseline" in err2
    # document/add on new FMEA (baseline=None) → ok
    cand_new = {**cand_existing, "baseline_version": None, "existing_targets": []}
    assert _validate_key_point(
        {"expected_action": "add", "target_kind": "document"}, cand_new
    ) is None
    # document/add on new CP (baseline=None) → ok (was wrongly fmea-only)
    cand_cp = {
        "doc_type": "control_plan", "existing_targets": [], "add_anchors": [],
        "baseline_version": None,
    }
    assert _validate_key_point(
        {"expected_action": "add", "target_kind": "document"}, cand_cp
    ) is None


def test_delete_field_must_be_in_allowed_fields():
    """delete with field outside allowed_fields → validation error."""
    cand = {
        "doc_type": "fmea",
        "existing_targets": [{"target_kind": "fmea_node", "target_key": "node-1",
                             "allowed_fields": ["prevention_control", "detection_control"]}],
        "add_anchors": [],
        "baseline_version": {"major": 1, "minor": 0, "sha256": "x"},
    }
    err = _validate_key_point(
        {"expected_action": "delete", "target_kind": "fmea_node",
         "target_key": "node-1", "field": "totally_fake"},
        cand,
    )
    assert err is not None and "field" in err


def test_non_object_llm_output_returns_error_string():
    """Non-dict docs/key_points must not AttributeError — return validation error."""
    cand = {
        "doc_type": "fmea", "doc_id": "d1", "doc_name": "F",
        "baseline_version_id": None, "baseline_version": None,
        "existing_targets": [], "add_anchors": [],
    }
    r1 = _validate_and_backfill({"affected_docs": [None]}, [cand])
    assert isinstance(r1, str) and "对象" in r1
    r2 = _validate_and_backfill(
        {"affected_docs": [{"doc_id": "d1", "key_points": [None], "update_suggestion": "s"}]},
        [cand],
    )
    assert isinstance(r2, str) and "对象" in r2


def test_match_document_only_covers_add():
    """Defensive: document/delete must not auto-pass even if it reaches match."""
    assert _match_key_point(
        {"expected_action": "add", "target_kind": "document"}, {}, None, "fmea"
    ) is True
    assert _match_key_point(
        {"expected_action": "delete", "target_kind": "document", "target_key": "x"},
        {}, None, "fmea",
    ) is False


def test_validate_rejects_duplicate_docs_and_delete_unknown_target():
    cand = {
        "doc_type": "fmea", "doc_id": "d1", "doc_name": "F",
        "baseline_version_id": "v1",
        "baseline_version": {"major": 1, "minor": 0, "sha256": "x"},
        "existing_targets": [{"target_kind": "fmea_node", "target_key": "node-1",
                             "allowed_fields": ["prevention_control"]}],
        "add_anchors": [],
    }
    # delete unknown target_key
    err = _validate_key_point(
        {"expected_action": "delete", "target_kind": "fmea_node", "target_key": "nope"},
        cand,
    )
    assert err is not None and "allowlist" in err
    # duplicate docs
    phase2 = {
        "affected_docs": [
            {"doc_id": "d1", "key_points": [
                {"expected_action": "modify", "target_kind": "fmea_node",
                 "field": "prevention_control", "target_key": "node-1"}
            ], "update_suggestion": "s"},
            {"doc_id": "d1", "key_points": [
                {"expected_action": "modify", "target_kind": "fmea_node",
                 "field": "prevention_control", "target_key": "node-1"}
            ], "update_suggestion": "s2"},
        ]
    }
    r = _validate_and_backfill(phase2, [cand])
    assert isinstance(r, str) and "重复" in r


# ---------------------------------------------------------------------------
# P1#5: empty affected_docs from LLM → done (not failed); confirm_no_affected path
# ---------------------------------------------------------------------------


def test_validate_and_backfill_accepts_empty_list():
    """LLM returning [] is a valid done state (spec C4), not a validation error."""
    result = _validate_and_backfill({"affected_docs": []}, candidates=[])
    assert result == []


@pytest.mark.asyncio
async def test_empty_llm_output_produces_done_analysis(db, capa_d8_gate_with_docs, docg_llm_mock):
    """LLM returns affected_docs=[] → analysis done with empty list → confirm_no_affected → passed."""
    capa, user = capa_d8_gate_with_docs
    docg_llm_mock.return_value = {"affected_docs": []}
    result = await capa_doc_gate_service.generate_impact_analysis(db, capa, user.user_id)
    assert result["status"] == "done"
    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(CapaDocgAnalysis.is_current == True)
    )
    assert analysis is not None
    assert analysis.status == "done"
    assert analysis.affected_docs == []
    # confirm_no_affected now reachable
    conf = await capa_doc_gate_service.confirm_no_affected(db, capa, user.user_id)
    assert conf["decision"] == "passed"
    assert conf["no_affected_confirmed"] is True


# ---------------------------------------------------------------------------
# P0#2 end-to-end: wrong-field bump → audit incomplete (not passed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_field_bump_does_not_pass_audit(db, capa_d8_gate_with_docs):
    """Analysis requires prevention_control change; bump only changes description → incomplete/blocked."""
    from app.models.fmea import FMEADocument
    from app.services.version_service import get_latest_fmea_version
    from tests.capa.conftest import _make_done_analysis

    capa, user = capa_d8_gate_with_docs
    fmea = await db.get(FMEADocument, capa.fmea_ref_id)
    baseline_ver = await get_latest_fmea_version(db, fmea.fmea_id)
    baseline_version = {"major": baseline_ver.major_no, "minor": baseline_ver.minor_no, "sha256": baseline_ver.sha256_hash}

    # Bump that only changes description (NOT prevention_control)
    wrong_snap = {
        "nodes": [{"id": "node-1", "type": "ProcessStep", "name": "step1", "description": "changed-desc"}],
        "edges": [],
    }
    fmea.graph_data = wrong_snap
    await db.execute(text(
        "INSERT INTO fmea_versions (version_id, fmea_id, factory_id, major_no, minor_no, "
        "snapshot, sha256_hash, change_summary, change_type, created_by, created_at) "
        "VALUES (:vid, :fid, :fact, 1, 1, CAST(:snap AS JSONB), "
        "encode(digest(CAST(:snap AS JSONB)::text, 'sha256'), 'hex'), "
        "'wrong-field', 'minor', :uid, NOW())"
    ), {
        "vid": uuid.uuid4(), "fid": fmea.fmea_id, "fact": capa.factory_id,
        "snap": json.dumps(wrong_snap), "uid": user.user_id,
    })
    await db.flush()

    affected = [{
        "doc_type": "fmea", "doc_id": str(capa.fmea_ref_id), "doc_name": "DocGate FMEA",
        "baseline_version_id": str(baseline_ver.version_id), "baseline_version": baseline_version,
        "key_points": [{"target_kind": "fmea_node", "expected_action": "modify",
                        "field": "prevention_control", "target_key": "node-1"}],
        "update_suggestion": "更新预防控制",
    }]
    await _make_done_analysis(db, capa, user, affected)

    result = await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    assert result["decision"] == "blocked"
    # Coverage for the key_point is False (wrong field)
    assert any(
        a["status"] == "incomplete" and a["covered_count"] == 0
        for a in result["audits"]
    )
