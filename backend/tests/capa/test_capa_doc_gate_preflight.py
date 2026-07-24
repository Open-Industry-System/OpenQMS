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
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
from app.models.control_plan import ControlPlan
from app.services.capa_doc_gate_preflight import scan_tenant_breaks


def test_preflight_docstring_uses_current_release_and_complete_waiver_shape():
    from app.services import capa_doc_gate_preflight

    doc = capa_doc_gate_preflight.__doc__ or ""
    assert "make deploy-check" not in doc
    assert "make deploy-release" in doc
    assert "audit_run_id" in doc
    assert "reason" in doc
    assert "items" in doc


def test_preflight_reuses_public_item_snapshot_parser():
    from app.services import capa_doc_gate_preflight, capa_doc_gate_waiver

    assert (
        capa_doc_gate_preflight.item_ids_from_snapshot
        is capa_doc_gate_waiver.item_ids_from_snapshot
    )
    assert capa_doc_gate_waiver.item_ids_from_snapshot(
        {"items": [{"item_id": "item-1"}, {"missing": "ignored"}]}
    ) == {"item-1"}


async def _seed_cp_with_version(
    db, factory_id, user_id, item_ids, created_at,
    product_line_code="DC-DC-100",
):
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-PRE-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code=product_line_code,
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
        capa.product_line_code,
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
        capa.product_line_code,
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
        capa.product_line_code,
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
        capa.product_line_code,
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
        capa.product_line_code,
    )
    await _add_cp_version(db, cp.cp_id, capa.factory_id, user.user_id, ["new-id"], 1, 1)
    breaks = await scan_tenant_breaks(db, "public")
    assert any(
        b["kind"] == "potential_disconnect" and b["cp_id"] == str(cp.cp_id)
        for b in breaks
    )


@pytest.mark.asyncio
async def test_preflight_blocks_stale_analysis_before_consuming_waiver(
    db, capa_with_cp_blocked_modify,
):
    """C9 semantic-input drift must block deploy even with a valid waiver."""
    from app.services import capa_doc_gate_service

    capa, user, cp, target_key, field = capa_with_cp_blocked_modify
    await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    await capa_doc_gate_service.record_gate_waiver(
        db, capa, "accepted",
        [{"doc_type": "control_plan", "doc_id": str(cp.cp_id),
          "target_key": target_key, "field": field}],
        user.user_id,
    )
    capa.d4_root_cause = "changed after analysis"
    await db.flush()

    breaks = await scan_tenant_breaks(db, "public")
    assert any(
        b["kind"] == "stale_analysis" and b["capa_id"] == str(capa.report_id)
        for b in breaks
    )


@pytest.mark.asyncio
async def test_preflight_invalid_waiver_does_not_suppress_blocked_modify(
    db, capa_with_cp_blocked_modify,
):
    """Persisted waiver tampering must block deploy and expose the lineage break."""
    from app.services import capa_doc_gate_service

    capa, user, cp, target_key, field = capa_with_cp_blocked_modify
    await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    await capa_doc_gate_service.record_gate_waiver(
        db, capa, "accepted",
        [{"doc_type": "control_plan", "doc_id": str(cp.cp_id),
          "target_key": target_key, "field": field}],
        user.user_id,
    )
    analysis = await db.scalar(select(CapaDocgAnalysis).where(
        CapaDocgAnalysis.capa_id == capa.report_id,
        CapaDocgAnalysis.is_current == True,  # noqa: E712
    ))
    decision = await db.scalar(
        select(CapaDocgDecision)
        .where(CapaDocgDecision.analysis_id == analysis.analysis_id)
        .order_by(CapaDocgDecision.revision.desc())
        .limit(1)
    )
    tampered = dict(decision.waiver_items[0])
    tampered["audit_run_id"] = str(uuid.uuid4())
    decision.waiver_items = [tampered]
    await db.flush()

    breaks = await scan_tenant_breaks(db, "public")
    assert any(
        b["kind"] == "invalid_waiver" and b["capa_id"] == str(capa.report_id)
        for b in breaks
    )
    assert any(
        b["kind"] == "blocked_modify"
        and b["blocked_modify_target_key"] == target_key
        for b in breaks
    )


@pytest.mark.asyncio
async def test_preflight_rejects_waiver_replaced_after_validation(
    sessionmaker, monkeypatch,
):
    """A newer decision committed by another session invalidates waiver N."""
    from app.models.factory import Factory
    from app.models.role import RoleDefinition
    from app.models.user import User
    from app.services import capa_doc_gate_service, capa_doc_gate_waiver

    suffix = uuid.uuid4().hex[:10]
    factory_id, role_id, user_id, capa_id = (
        uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    )
    analysis_id = cp_id = None
    target_key, field = "old-item", "control_method"

    async with sessionmaker() as seed:
        seed.add(Factory(
            id=factory_id, code=f"P{suffix}", name="Preflight decision race",
        ))
        seed.add(RoleDefinition(
            id=role_id, role_key=f"preflight_race_{suffix}",
            name_zh="预检竞态", name_en="Preflight race",
            is_system=False, is_editable=True, is_active=True,
        ))
        await seed.flush()
        user = User(
            user_id=user_id, username=f"preflight_race_{suffix}",
            display_name="Preflight race",
            email=f"preflight-{suffix}@example.com", password_hash="test",
            role_id=role_id, legacy_role="quality_engineer",
            is_active=True, factory_id=factory_id,
        )
        seed.add(user)
        await seed.flush()
        capa = CAPAEightD(
            report_id=capa_id, document_no=f"CAPA-PREF-{suffix}",
            title="preflight race", product_line_code="DC-DC-100",
            factory_id=factory_id, status="D8_GATE_PENDING", severity="serious",
            d4_root_cause="root", d5_correction="correction",
            d7_prevention="prevention", created_by=user_id,
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        seed.add(capa)
        await seed.flush()
        cp, baseline_id = await _seed_cp_with_version(
            seed, factory_id, user_id, [target_key],
            capa.created_at - timedelta(days=2),
        )
        cp_id = cp.cp_id
        await _add_cp_version(
            seed, cp_id, factory_id, user_id, ["new-item"], 1, 1,
        )
        affected_docs = _affected(cp_id, baseline_id, [{
            "target_kind": "cp_item", "expected_action": "modify",
            "field": field, "target_key": target_key,
        }])
        analysis = await _make_analysis(
            seed, capa, user_id, affected_docs, baseline_id,
        )
        analysis_id = analysis.analysis_id
        await seed.commit()
        await capa_doc_gate_service.run_audit(seed, capa, user_id)
        await capa_doc_gate_service.record_gate_waiver(
            seed, capa, "accepted",
            [{"doc_type": "control_plan", "doc_id": str(cp_id),
              "target_key": target_key, "field": field}],
            user_id,
        )
        waiver_n = await seed.scalar(
            select(CapaDocgDecision)
            .where(CapaDocgDecision.analysis_id == analysis_id)
            .order_by(CapaDocgDecision.revision.desc())
            .limit(1)
        )

    validate = capa_doc_gate_waiver.validate_persisted_waiver

    async def _commit_n_plus_one_after_validation(*args, **kwargs):
        waived_keys = await validate(*args, **kwargs)
        async with sessionmaker() as writer:
            writer.add(CapaDocgDecision(
                analysis_id=analysis_id,
                revision=waiver_n.revision + 1,
                factory_id=factory_id,
                decision="blocked",
                no_affected_confirmed=False,
                version_snapshot=[],
                decided_by=user_id,
            ))
            await writer.commit()
        return waived_keys

    monkeypatch.setattr(
        capa_doc_gate_waiver,
        "validate_persisted_waiver",
        _commit_n_plus_one_after_validation,
    )

    try:
        async with sessionmaker() as scanner:
            breaks = await scan_tenant_breaks(scanner, "public")

        assert sum(b["kind"] == "invalid_waiver" for b in breaks) == 1
        assert any(
            b["kind"] == "invalid_waiver"
            and "latest decision changed" in b["reason"]
            for b in breaks
        )
        assert any(
            b["kind"] == "blocked_modify"
            and b["blocked_modify_target_key"] == target_key
            for b in breaks
        )
    finally:
        async with sessionmaker() as cleanup:
            await cleanup.execute(text(
                "ALTER TABLE control_plan_versions "
                "DISABLE TRIGGER trg_cp_version_no_update"
            ))
            for statement in (
                "DELETE FROM audit_logs WHERE factory_id=:fid",
                "DELETE FROM capa_docg_decision WHERE analysis_id=:aid",
                "DELETE FROM capa_docg_audit WHERE analysis_id=:aid",
                "DELETE FROM capa_docg_analysis WHERE analysis_id=:aid",
                "DELETE FROM control_plan_versions WHERE cp_id=:cpid",
                "DELETE FROM control_plans WHERE cp_id=:cpid",
                "DELETE FROM capa_eightd WHERE report_id=:cid",
                "DELETE FROM users WHERE user_id=:uid",
                "DELETE FROM role_definitions WHERE id=:rid",
                "DELETE FROM factories WHERE id=:fid",
            ):
                await cleanup.execute(text(statement), {
                    "aid": analysis_id, "cpid": cp_id, "cid": capa_id,
                    "uid": user_id, "rid": role_id, "fid": factory_id,
                })
            await cleanup.execute(text(
                "ALTER TABLE control_plan_versions "
                "ENABLE TRIGGER trg_cp_version_no_update"
            ))
            await cleanup.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("v3_item_id", "expect_blocked"),
    [("newer-item", True), ("old-item", False)],
)
async def test_preflight_detects_version_drift_between_waiver_validation_and_scan(
    db, capa_with_cp_blocked_modify, monkeypatch, v3_item_id, expect_blocked,
):
    """A waiver validated on V2 is invalid once the lineage scan observes V3."""
    from types import SimpleNamespace
    from app.services import (
        capa_doc_gate_preflight,
        capa_doc_gate_service,
        capa_doc_gate_waiver,
    )
    from app.services.version_service import get_latest_cp_version

    capa, user, cp, target_key, field = capa_with_cp_blocked_modify
    await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    await capa_doc_gate_service.record_gate_waiver(
        db, capa, "accepted",
        [{"doc_type": "control_plan", "doc_id": str(cp.cp_id),
          "target_key": target_key, "field": field}],
        user.user_id,
    )
    audited_v2 = await get_latest_cp_version(db, cp.cp_id)
    drifted_v3 = SimpleNamespace(
        version_id=uuid.uuid4(),
        sha256_hash="3" * 64,
        items_snapshot=[{"item_id": v3_item_id, "control_method": "m3"}],
    )

    async def _validator_reads_v2(_db, _cp_id):
        return audited_v2

    async def _lineage_scan_reads_v3(_db, _cp_id):
        return drifted_v3

    monkeypatch.setattr(
        capa_doc_gate_waiver, "get_latest_cp_version", _validator_reads_v2
    )
    monkeypatch.setattr(
        capa_doc_gate_preflight, "get_latest_cp_version", _lineage_scan_reads_v3
    )

    breaks = await scan_tenant_breaks(db, "public")
    assert sum(b["kind"] == "invalid_waiver" for b in breaks) == 1
    has_blocked_modify = any(
        b["kind"] == "blocked_modify"
        and b["blocked_modify_target_key"] == target_key
        and b["latest_version_id"] == str(drifted_v3.version_id)
        for b in breaks
    )
    assert has_blocked_modify is expect_blocked


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
async def test_verify_fmea_version_accepts_legacy_compact_hash(db, capa_d8_gate):
    """FMEA historical compact-JSON hashes must still verify (dual-algorithm)."""
    from app.models.fmea import FMEADocument
    from app.models.fmea_version import FMEAVersion
    from app.services.version_service import compute_snapshot_hash, verify_fmea_version
    from sqlalchemy import text as _text
    capa, user = capa_d8_gate
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-LEG-{uuid.uuid4().hex[:6]}",
        title="t", fmea_type="PFMEA", product_line_code="DC-DC-100",
        factory_id=capa.factory_id, status="approved",
        created_by=user.user_id, graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea)
    await db.flush()
    snap = {"nodes": [{"id": "n1"}], "edges": []}
    ver = FMEAVersion(
        version_id=uuid.uuid4(), fmea_id=fmea.fmea_id, factory_id=capa.factory_id,
        major_no=1, minor_no=0, snapshot=snap, sha256_hash="placeholder",
        change_type="approve", change_summary="legacy", created_by=user.user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(ver)
    await db.flush()
    compact = compute_snapshot_hash(snap)
    await db.execute(_text("ALTER TABLE fmea_versions DISABLE TRIGGER trg_fmea_version_no_update"))
    await db.execute(_text(
        "UPDATE fmea_versions SET sha256_hash=:h WHERE version_id=:vid"
    ), {"h": compact, "vid": ver.version_id})
    await db.execute(_text("ALTER TABLE fmea_versions ENABLE TRIGGER trg_fmea_version_no_update"))
    await db.refresh(ver)
    assert ver.sha256_hash == compact
    assert await verify_fmea_version(db, ver.version_id) is True


@pytest.mark.asyncio
async def test_hash_backfill_demotes_all_current_analyses(db, capa_with_done_analysis_and_bumped_doc):
    """Hash backfill demotes EVERY current analysis (full C9 fail-closed), not only
    those whose affected_docs baseline hash mismatches. Empty lists / unselected
    candidates still embed hashes in analysis_input_hash."""
    from app.models.capa_doc_gate import CapaDocgAnalysis
    from sqlalchemy import text as _text
    capa, user = capa_with_done_analysis_and_bumped_doc
    analysis = (await db.execute(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.is_current == True  # noqa: E712
        )
    )).scalar_one()
    assert analysis.is_current is True
    # Migration demote is unconditional for is_current=true
    await db.execute(_text("""
        UPDATE capa_docg_analysis
        SET is_current = false,
            error = COALESCE(error || ' | ', '') || 'demoted by hash backfill migration (C9 full demote)'
        WHERE is_current = true
    """))
    await db.flush()
    await db.refresh(analysis)
    assert analysis.is_current is False
    assert "demoted by hash backfill" in (analysis.error or "")


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
