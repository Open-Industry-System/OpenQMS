"""Tests for capa_doc_gate_preflight (US-E2E-01.7).

Covers: open-CAPA scope, modify-vs-delete precision, shared-id partial break,
terminal-CAPA skip. CP versions inserted via raw SQL (sha256_hash=NULL skips
the verify_version_hash trigger which expects a `snapshot` column absent on
control_plan_versions).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select, text

from app.models.capa import CAPAEightD
from app.models.capa_doc_gate import CapaDocgAnalysis
from app.models.control_plan import ControlPlan
from app.services.capa_doc_gate_preflight import scan_tenant_breaks


async def _seed_cp_with_version(db, factory_id, user_id, item_ids, created_at):
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-PRE-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        status="approved",
        created_by=user_id,
    )
    db.add(cp)
    await db.flush()
    items = [{"item_id": iid, "source_fmea_node_id": "s", "product_characteristic": "x",
              "control_method": "m"} for iid in item_ids]
    await _insert_cp_version(db, cp.cp_id, factory_id, user_id, 1, 0, items, created_at, "approve", "initial")
    vid = uuid.uuid4()
    # fetch the inserted version_id
    row = (await db.execute(text(
        "SELECT version_id FROM control_plan_versions WHERE cp_id=:cp ORDER BY created_at LIMIT 1"
    ), {"cp": cp.cp_id})).scalar_one()
    return cp, row


async def _insert_cp_version(db, cp_id, factory_id, user_id, major, minor, items, created_at=None,
                             change_type="minor", change_summary="rebuild"):
    """Insert a CP version with a hash matching the verify_version_hash trigger
    (jsonb_build_object combined ::text, PG default separators)."""
    items_json = json.dumps(items)
    await db.execute(text(
        "INSERT INTO control_plan_versions (version_id, cp_id, factory_id, major_no, minor_no, "
        "header_snapshot, items_snapshot, sha256_hash, change_type, change_summary, "
        "created_by, created_at) VALUES ("
        ":vid, :cp, :fact, :major, :minor, '{}'::jsonb, CAST(:items AS JSONB), "
        "encode(digest(jsonb_build_object('header','{}'::jsonb,'items',CAST(:items AS JSONB))::text,'sha256'),'hex'), "
        ":ctype, :csum, :uid, COALESCE(:ca, NOW()))"
    ), {
        "vid": uuid.uuid4(), "cp": cp_id, "fact": factory_id, "major": major, "minor": minor,
        "items": items_json, "ctype": change_type, "csum": change_summary,
        "uid": user_id, "ca": created_at,
    })
    await db.flush()


async def _add_cp_version(db, cp_id, factory_id, user_id, item_ids, major, minor):
    items = [{"item_id": iid, "source_fmea_node_id": "s", "product_characteristic": "x",
              "control_method": "m"} for iid in item_ids]
    await _insert_cp_version(db, cp_id, factory_id, user_id, major, minor, items)


async def _make_analysis(db, capa, user_id, affected_docs, baseline_version_id):
    from app.services.capa_doc_gate_service import _build_allowlist, _compute_input_hash
    candidates = await _build_allowlist(db, capa)
    a = CapaDocgAnalysis(
        analysis_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=capa.factory_id,
        is_current=True, status="done", affected_docs=affected_docs,
        analysis_input_hash=_compute_input_hash(capa, candidates),
        llm_available=True, model="test", completed_at=datetime.now(timezone.utc),
        generated_by=user_id,
    )
    db.add(a)
    await db.flush()
    return a


def _affected(cp_id, baseline_version_id, kps):
    return [{
        "doc_type": "control_plan", "doc_id": str(cp_id), "doc_name": "CP",
        "baseline_version_id": str(baseline_version_id),
        "baseline_version": {"major": 1, "minor": 0, "sha256": "h"},
        "key_points": kps, "update_suggestion": "s",
    }]


@pytest.mark.asyncio
async def test_preflight_reports_modify_target_absent_from_latest(db, capa_d8_gate):
    """modify target_key absent from latest → break."""
    capa, user = capa_d8_gate
    cp, ver = await _seed_cp_with_version(
        db, capa.factory_id, user.user_id,
        ["old-id"], capa.created_at - timedelta(days=2),
    )
    await _add_cp_version(db, cp.cp_id, capa.factory_id, user.user_id, ["new-id"], 1, 1)
    kps = [{"target_kind": "cp_item", "expected_action": "modify",
            "field": "control_method", "target_key": "old-id"}]
    await _make_analysis(db, capa, user.user_id, _affected(cp.cp_id, ver, kps), ver)
    breaks = await scan_tenant_breaks(db, "public")
    assert any(b["blocked_modify_target_key"] == "old-id" for b in breaks)


@pytest.mark.asyncio
async def test_preflight_does_not_report_delete_target_absent(db, capa_d8_gate):
    """delete target_key absent from latest → NOT a break (expected outcome)."""
    capa, user = capa_d8_gate
    cp, ver = await _seed_cp_with_version(
        db, capa.factory_id, user.user_id,
        ["old-id"], capa.created_at - timedelta(days=2),
    )
    await _add_cp_version(db, cp.cp_id, capa.factory_id, user.user_id, [], 1, 1)
    kps = [{"target_kind": "cp_item", "expected_action": "delete",
            "field": "control_method", "target_key": "old-id"}]
    await _make_analysis(db, capa, user.user_id, _affected(cp.cp_id, ver, kps), ver)
    breaks = await scan_tenant_breaks(db, "public")
    assert breaks == []


@pytest.mark.asyncio
async def test_preflight_partial_shared_id_reports_only_blocked_modify(db, capa_d8_gate):
    """baseline {A,B}, latest {A,C}: modify B blocked even though A shared."""
    capa, user = capa_d8_gate
    cp, ver = await _seed_cp_with_version(
        db, capa.factory_id, user.user_id,
        ["A", "B"], capa.created_at - timedelta(days=2),
    )
    await _add_cp_version(db, cp.cp_id, capa.factory_id, user.user_id, ["A", "C"], 1, 1)
    kps = [
        {"target_kind": "cp_item", "expected_action": "modify",
         "field": "control_method", "target_key": "A"},
        {"target_kind": "cp_item", "expected_action": "modify",
         "field": "control_method", "target_key": "B"},
    ]
    await _make_analysis(db, capa, user.user_id, _affected(cp.cp_id, ver, kps), ver)
    breaks = await scan_tenant_breaks(db, "public")
    assert {b["blocked_modify_target_key"] for b in breaks} == {"B"}


@pytest.mark.asyncio
async def test_preflight_skips_terminal_capa(db, capa_d8_gate):
    """D8_CLOSURE CAPAs are not scanned."""
    capa, user = capa_d8_gate
    capa.status = "D8_CLOSURE"
    await db.flush()
    cp, ver = await _seed_cp_with_version(
        db, capa.factory_id, user.user_id,
        ["old-id"], capa.created_at - timedelta(days=2),
    )
    await _add_cp_version(db, cp.cp_id, capa.factory_id, user.user_id, ["new-id"], 1, 1)
    kps = [{"target_kind": "cp_item", "expected_action": "modify",
            "field": "control_method", "target_key": "old-id"}]
    await _make_analysis(db, capa, user.user_id, _affected(cp.cp_id, ver, kps), ver)
    breaks = await scan_tenant_breaks(db, "public")
    assert breaks == []

