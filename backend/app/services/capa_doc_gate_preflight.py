"""Preflight: detect CP item_id lineage breaks that block the D8 doc-gate.

US-E2E-01.7 contract v2 uses item_id as the stable target_key for CP modify/
delete coverage.

Two scan modes (both over open CAPAs only, all active tenant schemas):

1. **With current analysis** (exit 1 if any) — each cp_item *modify* key_point
   whose target_key is absent from the latest CP version (get_latest_cp_version).
   delete targets that disappeared are NOT reported.

2. **Without analysis** (exit 0 WARN unless --strict-potential) — candidate CPs
   (same factory + product line) where baseline (created_at <= capa.created_at)
   item_ids share ZERO overlap with latest. Advisory: gate not yet blocked.

Exit codes:
  0 — no blocking finding (potential_disconnect alone warns unless --strict-potential)
  1 — blocked_modify, stale_analysis, invalid_waiver (or strict potential)

Deploy: run against TARGET DB (DATABASE_URL), not TEST_DATABASE_URL.
  make doc-gate-preflight
  make deploy-check   # check + preflight (release gate)

Remediation (executable — re-analysis alone never changes CAPA-time baseline):
  blocked_modify:
    (a) Re-author the CP under the item_id-preserving save path, then demote the
        current analysis and regenerate so a NEW current analysis references
        continuing ids. (Note: baseline is frozen at capa.created_at — only NEW
        CAPAs created after the CP re-save get a clean baseline; for an existing
        blocked CAPA use (b).)
    (b) Manager-authorized waiver: POST /capa/{id}/doc-gate/waiver {reason}.
        Requires APPROVE permission on the capa module. Audited (DOC_GATE_WAIVER
        + decision row with waiver_reason) and forces decision=passed so the
        CAPA can advance to D8_APPROVAL_PENDING. Use when the break is an
        intentional delete+add that the team accepts.
    The state machine forbids archiving D8_GATE_PENDING directly, so (a)/(b)
    are the only on-rails paths — do NOT attempt to close the CAPA to clear it.
  potential_disconnect:
    (a)/(b) before this CAPA reaches D8 with modify key_points on those ids.

Usage:
    python -m app.services.capa_doc_gate_preflight
    python -m app.services.capa_doc_gate_preflight --json
    python -m app.services.capa_doc_gate_preflight --strict-potential
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import run_for_each_tenant
from app.models.capa import CAPAEightD
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
from app.models.control_plan import ControlPlan
from app.models.control_plan_version import ControlPlanVersion
from app.services.version_service import get_latest_cp_version
from app.state_machines.eightd_state import is_capa_open_value


def _item_ids_from_snapshot(items_snapshot) -> set[str]:
    if items_snapshot is None:
        return set()
    if isinstance(items_snapshot, dict):
        items = items_snapshot.get("items", [])
    elif isinstance(items_snapshot, list):
        items = items_snapshot
    else:
        return set()
    return {str(i.get("item_id")) for i in items if isinstance(i, dict) and i.get("item_id")}


async def _baseline_cp_version(db: AsyncSession, cp_id: uuid.UUID, capa_created_at):
    """Last CP version with created_at <= capa.created_at (matches doc-gate baseline)."""
    result = await db.execute(
        select(ControlPlanVersion)
        .where(
            ControlPlanVersion.cp_id == cp_id,
            ControlPlanVersion.created_at <= capa_created_at,
        )
        .order_by(
            ControlPlanVersion.created_at.desc(),
            ControlPlanVersion.major_no.desc(),
            ControlPlanVersion.minor_no.desc(),
            ControlPlanVersion.version_id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _waiver_identity_drift_reason(
    db: AsyncSession,
    capa_id: uuid.UUID,
    analysis: CapaDocgAnalysis,
    decision: CapaDocgDecision,
) -> str | None:
    """Re-read waiver ownership immediately before preflight suppression."""
    current_analysis_id = await db.scalar(
        select(CapaDocgAnalysis.analysis_id)
        .where(
            CapaDocgAnalysis.capa_id == capa_id,
            CapaDocgAnalysis.is_current == True,  # noqa: E712
        )
        .limit(1)
    )
    if current_analysis_id != analysis.analysis_id:
        return (
            "waiver analysis changed between validation and lineage scan: "
            f"validated={analysis.analysis_id} current={current_analysis_id}"
        )

    latest_decision = (await db.execute(
        select(CapaDocgDecision.decision_id, CapaDocgDecision.revision)
        .where(CapaDocgDecision.analysis_id == analysis.analysis_id)
        .order_by(CapaDocgDecision.revision.desc())
        .limit(1)
    )).one_or_none()
    validated_identity = (decision.decision_id, decision.revision)
    if latest_decision is None or tuple(latest_decision) != validated_identity:
        latest_identity = None if latest_decision is None else tuple(latest_decision)
        return (
            "waiver latest decision changed between validation and lineage scan: "
            f"validated={validated_identity} latest={latest_identity}"
        )
    return None


async def scan_tenant_breaks(db: AsyncSession, tenant_schema: str) -> list[dict]:
    """Report blocked/potential CP item_id lineage breaks for open CAPAs."""
    breaks: list[dict] = []
    open_capas = [
        c for c in (await db.execute(select(CAPAEightD))).scalars().all()
        if is_capa_open_value(c.status)
    ]
    if not open_capas:
        return breaks
    capa_by_id = {c.report_id: c for c in open_capas}
    capa_ids = set(capa_by_id)

    analyses = (await db.execute(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.is_current == True,  # noqa: E712
            CapaDocgAnalysis.capa_id.in_(capa_ids),
        )
    )).scalars().all()
    # Read latest revision per analysis once. The shared waiver validator trusts
    # the caller's latest selection; unlike runtime gate this scanner takes no
    # analysis/parent row locks across its multi-tenant read transaction.
    analysis_ids = [a.analysis_id for a in analyses]
    latest_decision_by_analysis: dict[uuid.UUID, CapaDocgDecision] = {}
    if analysis_ids:
        from sqlalchemy import func as sa_func
        latest_rev = (
            select(
                CapaDocgDecision.analysis_id,
                sa_func.max(CapaDocgDecision.revision).label("max_rev"),
            )
            .where(CapaDocgDecision.analysis_id.in_(analysis_ids))
            .group_by(CapaDocgDecision.analysis_id)
            .subquery()
        )
        latest_decs = (await db.execute(
            select(CapaDocgDecision).join(
                latest_rev,
                (CapaDocgDecision.analysis_id == latest_rev.c.analysis_id)
                & (CapaDocgDecision.revision == latest_rev.c.max_rev),
            )
        )).scalars().all()
        for dec in latest_decs:
            latest_decision_by_analysis[dec.analysis_id] = dec
    analyzed_capa_ids: set[uuid.UUID] = set()
    for analysis in analyses:
        capa = capa_by_id.get(analysis.capa_id)
        if capa is None:
            continue
        analyzed_capa_ids.add(capa.report_id)
        from app.services.capa_doc_gate_service import _build_allowlist, _compute_input_hash
        candidates = await _build_allowlist(db, capa)
        current_input_hash = _compute_input_hash(capa, candidates)
        if current_input_hash != analysis.analysis_input_hash:
            breaks.append({
                "kind": "stale_analysis",
                "tenant_schema": tenant_schema,
                "capa_id": str(capa.report_id),
                "capa_document_no": capa.document_no,
                "capa_status": capa.status,
                "analysis_id": str(analysis.analysis_id),
                "reason": "C9 analysis_input_hash mismatch",
            })
            continue

        waived_keys: dict[tuple[str, str, str], tuple[str, str]] = {}
        invalid_waiver_reported = False
        decision = latest_decision_by_analysis.get(analysis.analysis_id)
        if decision is not None and (
            decision.waiver_reason is not None or decision.waiver_items is not None
        ):
            from app.services.capa_doc_gate_waiver import validate_persisted_waiver
            try:
                waived_keys = await validate_persisted_waiver(
                    db, analysis, decision, lock_version_parents=False
                )
            except ValueError as exc:
                breaks.append({
                    "kind": "invalid_waiver",
                    "tenant_schema": tenant_schema,
                    "capa_id": str(capa.report_id),
                    "capa_document_no": capa.document_no,
                    "capa_status": capa.status,
                    "analysis_id": str(analysis.analysis_id),
                    "decision_id": str(decision.decision_id),
                    "reason": str(exc),
                })
                waived_keys = {}
                invalid_waiver_reported = True
        if not analysis.affected_docs:
            continue
        for doc in analysis.affected_docs:
            if not isinstance(doc, dict) or doc.get("doc_type") != "control_plan":
                continue
            try:
                cp_id = uuid.UUID(str(doc["doc_id"]))
            except (ValueError, TypeError):
                continue
            latest_ver = await get_latest_cp_version(db, cp_id)
            if latest_ver is None:
                continue
            if waived_keys:
                identity_drift_reason = await _waiver_identity_drift_reason(
                    db, capa.report_id, analysis, decision
                )
                if identity_drift_reason is not None:
                    if not invalid_waiver_reported:
                        breaks.append({
                            "kind": "invalid_waiver",
                            "tenant_schema": tenant_schema,
                            "capa_id": str(capa.report_id),
                            "capa_document_no": capa.document_no,
                            "capa_status": capa.status,
                            "analysis_id": str(analysis.analysis_id),
                            "decision_id": str(decision.decision_id),
                            "reason": identity_drift_reason,
                        })
                        invalid_waiver_reported = True
                    waived_keys = {}
            drifted_binding = next((
                bound
                for (waived_doc_id, _target_key, _field), bound in waived_keys.items()
                if waived_doc_id == str(cp_id)
                and (
                    str(latest_ver.version_id) != bound[0]
                    or latest_ver.sha256_hash != bound[1]
                )
            ), None)
            if drifted_binding is not None:
                bound_version_id, bound_sha256 = drifted_binding
                if not invalid_waiver_reported:
                    breaks.append({
                        "kind": "invalid_waiver",
                        "tenant_schema": tenant_schema,
                        "capa_id": str(capa.report_id),
                        "capa_document_no": capa.document_no,
                        "capa_status": capa.status,
                        "analysis_id": str(analysis.analysis_id),
                        "decision_id": str(decision.decision_id),
                        "reason": (
                            "waiver version drift between validation and lineage scan: "
                            f"bound={bound_version_id}/{bound_sha256} "
                            f"latest={latest_ver.version_id}/{latest_ver.sha256_hash}"
                        ),
                    })
                    invalid_waiver_reported = True
                waived_keys = {}
            latest_ids = _item_ids_from_snapshot(latest_ver.items_snapshot)
            for kp in doc.get("key_points") or []:
                if not isinstance(kp, dict):
                    continue
                if kp.get("expected_action") != "modify" or kp.get("target_kind") != "cp_item":
                    continue
                tk = str(kp.get("target_key") or "").strip()
                field = str(kp.get("field") or "").strip()
                if not tk:
                    continue
                if tk not in latest_ids:
                    if (str(cp_id), tk, field) in waived_keys:
                        continue
                    breaks.append({
                        "kind": "blocked_modify",
                        "tenant_schema": tenant_schema,
                        "capa_id": str(capa.report_id),
                        "capa_document_no": capa.document_no,
                        "capa_status": capa.status,
                        "cp_id": str(cp_id),
                        "latest_version_id": str(latest_ver.version_id),
                        "blocked_modify_target_key": tk,
                        "blocked_field": field or kp.get("field"),
                    })

    for capa in open_capas:
        if capa.report_id in analyzed_capa_ids:
            continue
        cps = (await db.execute(
            select(ControlPlan).where(
                ControlPlan.factory_id == capa.factory_id,
                ControlPlan.product_line_code == capa.product_line_code,
            )
        )).scalars().all()
        for cp in cps:
            baseline = await _baseline_cp_version(db, cp.cp_id, capa.created_at)
            latest = await get_latest_cp_version(db, cp.cp_id)
            if baseline is None or latest is None:
                continue
            b_ids = _item_ids_from_snapshot(baseline.items_snapshot)
            l_ids = _item_ids_from_snapshot(latest.items_snapshot)
            if b_ids and l_ids and not (b_ids & l_ids):
                breaks.append({
                    "kind": "potential_disconnect",
                    "tenant_schema": tenant_schema,
                    "capa_id": str(capa.report_id),
                    "capa_document_no": capa.document_no,
                    "capa_status": capa.status,
                    "cp_id": str(cp.cp_id),
                    "baseline_version_id": str(baseline.version_id),
                    "latest_version_id": str(latest.version_id),
                    "baseline_item_ids": sorted(b_ids),
                    "latest_item_ids": sorted(l_ids),
                })
    return breaks


async def run_preflight(json_output: bool = False, strict_potential: bool = False) -> int:
    all_breaks: list[dict] = []
    async for tenant, db in run_for_each_tenant():
        all_breaks.extend(await scan_tenant_breaks(db, tenant.schema_name))
    blocked = [b for b in all_breaks if b["kind"] == "blocked_modify"]
    stale = [b for b in all_breaks if b["kind"] == "stale_analysis"]
    invalid_waivers = [b for b in all_breaks if b["kind"] == "invalid_waiver"]
    potential = [b for b in all_breaks if b["kind"] == "potential_disconnect"]
    blocking = blocked + stale + invalid_waivers

    if json_output:
        print(json.dumps({
            "breaks": all_breaks,
            "blocked_modify_count": len(blocked),
            "stale_analysis_count": len(stale),
            "invalid_waiver_count": len(invalid_waivers),
            "potential_disconnect_count": len(potential),
            "exit_blocks": bool(blocking) or (strict_potential and bool(potential)),
        }, ensure_ascii=False, indent=2))
    else:
        if not all_breaks:
            print("doc-gate CP lineage preflight: CLEAN (0 breaks)")
        else:
            if blocked:
                print(f"doc-gate CP lineage preflight: {len(blocked)} BLOCKED modify key_point(s) "
                      f"(exit 1 — deploy must not proceed):")
                for b in blocked:
                    print(f"  - [{b['tenant_schema']}] CAPA {b['capa_document_no']} "
                          f"({b['capa_id']}, {b['capa_status']})")
                    print(f"      CP {b['cp_id']}: modify target_key={b['blocked_modify_target_key']} "
                          f"field={b['blocked_field']} absent from latest v{b['latest_version_id']}")
                    print("      Executable remediation (re-analysis alone NEVER changes CAPA-time baseline):")
                    print("        (a) Re-author CP (item_id-preserving) + demote & regenerate analysis")
                    print("            so the new current analysis references continuing ids.")
                    print("        (b) Structured manager waiver (APPROVE; audited; exact keypoint only):")
                    print("            POST /capa/{id}/doc-gate/waiver")
                    _payload = (
                        '{"reason":"...", "items":[{"doc_type":"control_plan",'
                        '"doc_id":"%s","target_key":"%s","field":"%s"}]}'
                        % (b["cp_id"], b["blocked_modify_target_key"], b["blocked_field"])
                    )
                    print("            " + _payload)
                    print("            Server reconfirms live absence + audit coverage; other docs stay under C8.")
                    print("        State machine forbids archiving D8_GATE_PENDING directly.")
            if stale:
                print(f"doc-gate preflight: {len(stale)} STALE analysis finding(s) "
                      "(exit 1 — deploy must not proceed):")
                for b in stale:
                    print(f"  - [{b['tenant_schema']}] CAPA {b['capa_document_no']} "
                          f"({b['capa_id']}, {b['capa_status']}) analysis={b['analysis_id']}")
                    print("      C9 semantic/candidate input changed. Regenerate impact analysis,")
                    print("      rerun audit, and recreate any manager waiver before deploy.")
            if invalid_waivers:
                print(f"doc-gate preflight: {len(invalid_waivers)} INVALID waiver finding(s) "
                      "(exit 1 — deploy must not proceed):")
                for b in invalid_waivers:
                    print(f"  - [{b['tenant_schema']}] CAPA {b['capa_document_no']} "
                          f"({b['capa_id']}, {b['capa_status']}) decision={b['decision_id']}")
                    print(f"      reason: {b['reason']}")
                    print("      Rerun the document audit and create a fresh structured waiver;")
                    print("      the invalid waiver suppresses no blocked_modify keys.")
            if potential:
                print(f"doc-gate CP lineage preflight: {len(potential)} POTENTIAL disconnect(s) "
                      f"(WARN only; exit 0 unless --strict-potential):")
                for b in potential:
                    print(f"  - [{b['tenant_schema']}] CAPA {b['capa_document_no']} "
                          f"({b['capa_id']}, {b['capa_status']}) [no analysis yet]")
                    print(f"      CP {b['cp_id']}: baseline item_ids share NONE with latest "
                          f"(baseline={b['baseline_version_id']}, latest={b['latest_version_id']})")
                    print("      Before D8: re-author CP (item_id-preserving) so future analysis")
                    print("      freezes continuing ids, or plan only delete/add/document key_points.")

    if blocking:
        return 1
    if strict_potential and potential:
        return 1
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="US-E2E-01.7 doc-gate CP lineage preflight")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    p.add_argument(
        "--strict-potential",
        action="store_true",
        help="exit 1 also when potential_disconnect warnings exist",
    )
    args = p.parse_args()
    rc = asyncio.run(run_preflight(json_output=args.json, strict_potential=args.strict_potential))
    sys.exit(rc)


if __name__ == "__main__":
    main()
