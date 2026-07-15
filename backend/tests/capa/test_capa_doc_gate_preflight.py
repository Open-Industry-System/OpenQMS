"""Tests for capa_doc_gate_preflight (US-E2E-01.7).

Covers: open-CAPA scope, modify-vs-delete precision, shared-id partial break,
terminal-CAPA skip, no-analysis potential disconnect. CP versions use app
compute_snapshot_hash (compact JSON) matching the fixed trigger (hash required,
no PG jsonb::text re-verify).
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
    """Insert a CP version via production path: PG jsonb::text hash + ORM."""
    from app.models.control_plan_version import ControlPlanVersion
    from app.services.version_service import compute_pg_jsonb_hash
    header = {}
    combined = {"header": header, "items": items}
    sha = await compute_pg_jsonb_hash(db, combined)
    ver = ControlPlanVersion(
        version_id=uuid.uuid4(),
        cp_id=cp_id,
        factory_id=factory_id,
        major_no=major,
        minor_no=minor,
        header_snapshot=header,
        items_snapshot=items,
        sha256_hash=sha,
        change_type=change_type,
        change_summary=change_summary,
        created_by=user_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(ver)
    await db.flush()
    return ver.version_id


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


@pytest.mark.asyncio
async def test_preflight_no_analysis_reports_potential_disconnect(db, capa_d8_gate):
    """Open CAPA without analysis: baseline/latest zero item_id overlap → potential_disconnect."""
    capa, user = capa_d8_gate
    # No analysis for this capa. Seed a CP whose baseline ids share none with latest.
    cp, ver = await _seed_cp_with_version(
        db, capa.factory_id, user.user_id,
        ["old-id"], capa.created_at - timedelta(days=2),
    )
    await _add_cp_version(db, cp.cp_id, capa.factory_id, user.user_id, ["new-id"], 1, 1)
    breaks = await scan_tenant_breaks(db, "public")
    assert any(
        b["kind"] == "potential_disconnect" and b["cp_id"] == str(cp.cp_id)
        for b in breaks
    )


@pytest.mark.asyncio
async def test_create_cp_version_production_path_ok(db, capa_d8_gate):
    """Regression: create_cp_version must succeed after trigger fix (PG jsonb hash)."""
    from app.services.version_service import create_cp_version, verify_cp_version
    from app.models.control_plan import ControlPlanItem
    capa, user = capa_d8_gate
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-PROD-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=capa.factory_id,
        status="draft",
        created_by=user.user_id,
    )
    db.add(cp)
    await db.flush()
    db.add(ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
        product_characteristic="A", control_method="m",
        source_fmea_node_id="s", sort_order=0, factory_id=capa.factory_id,
    ))
    await db.flush()
    ver = await create_cp_version(db, cp, "approve", "ok", user.user_id)
    assert ver.sha256_hash
    assert ver.major_no == 1
    assert await verify_cp_version(db, ver.version_id) is True


@pytest.mark.asyncio
async def test_cp_version_trigger_binds_content_and_verify_accepts_pg_hash(db, capa_d8_gate):
    """Trigger overwrites sha256_hash from content; verify accepts PG digest."""
    from app.models.control_plan_version import ControlPlanVersion
    from app.services.version_service import compute_pg_jsonb_hash, verify_cp_version
    capa, user = capa_d8_gate
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-HASH-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=capa.factory_id,
        status="draft",
        created_by=user.user_id,
    )
    db.add(cp)
    await db.flush()
    header = {"title": "t"}
    items = [{"item_id": "i1", "control_method": "m"}]
    ver = ControlPlanVersion(
        version_id=uuid.uuid4(), cp_id=cp.cp_id, factory_id=capa.factory_id,
        major_no=1, minor_no=0, header_snapshot=header, items_snapshot=items,
        sha256_hash="x" * 64,  # forged — trigger must overwrite
        change_type="approve", change_summary="forge", created_by=user.user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(ver)
    await db.flush()
    await db.refresh(ver)
    expected = await compute_pg_jsonb_hash(db, {"header": header, "items": items})
    assert ver.sha256_hash == expected
    assert ver.sha256_hash != "x" * 64
    assert await verify_cp_version(db, ver.version_id) is True


@pytest.mark.asyncio
async def test_verify_cp_version_accepts_legacy_compact_hash(db, capa_d8_gate):
    """Historical compact-JSON hashes must still verify (dual-algorithm)."""
    from app.models.control_plan_version import ControlPlanVersion
    from app.services.version_service import compute_snapshot_hash, verify_cp_version
    from sqlalchemy import text as _text
    capa, user = capa_d8_gate
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-LEG-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=capa.factory_id,
        status="draft",
        created_by=user.user_id,
    )
    db.add(cp)
    await db.flush()
    header = {"title": "legacy"}
    items = [{"item_id": "i1", "control_method": "m"}]
    # Insert via trigger (gets PG hash), then rewrite to compact hash with immutability off
    ver = ControlPlanVersion(
        version_id=uuid.uuid4(), cp_id=cp.cp_id, factory_id=capa.factory_id,
        major_no=1, minor_no=0, header_snapshot=header, items_snapshot=items,
        sha256_hash="placeholder",
        change_type="approve", change_summary="legacy", created_by=user.user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(ver)
    await db.flush()
    compact = compute_snapshot_hash({"header": header, "items": items})
    await db.execute(_text("ALTER TABLE control_plan_versions DISABLE TRIGGER trg_cp_version_no_update"))
    await db.execute(_text(
        "UPDATE control_plan_versions SET sha256_hash=:h WHERE version_id=:vid"
    ), {"h": compact, "vid": ver.version_id})
    await db.execute(_text("ALTER TABLE control_plan_versions ENABLE TRIGGER trg_cp_version_no_update"))
    await db.refresh(ver)
    assert ver.sha256_hash == compact
    assert await verify_cp_version(db, ver.version_id) is True

