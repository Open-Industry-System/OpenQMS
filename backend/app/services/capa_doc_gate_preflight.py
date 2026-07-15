"""Preflight: detect CP item_id lineage breaks that block the D8 doc-gate.

US-E2E-01.7 contract v2 uses item_id as the stable target_key for CP modify/
delete coverage. A CAPA whose current analysis has a `modify` key_point whose
target_key (item_id) is absent from the latest CP version snapshot can never
satisfy that key_point — the gate will block indefinitely. Historical whole-
table UUID rebuild produced exactly such breaks.

This scan reports ONLY genuinely blocked modify key_points (not delete — a
delete target disappearing is the expected outcome, not a break). It iterates
all open (non-D8_CLOSURE/ARCHIVED) CAPAs across all active tenant schemas.

Exit code: 1 if any break found (blocks deployment), 0 otherwise.

Usage:
    python -m app.services.capa_doc_gate_preflight            # human-readable
    python -m app.services.capa_doc_gate_preflight --json      # machine-readable
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
from app.models.capa_doc_gate import CapaDocgAnalysis
from app.models.control_plan_version import ControlPlanVersion
from app.state_machines.eightd_state import is_capa_open_value


async def _latest_cp_version(db: AsyncSession, cp_id: uuid.UUID):
    result = await db.execute(
        select(ControlPlanVersion)
        .where(ControlPlanVersion.cp_id == cp_id)
        .order_by(
            ControlPlanVersion.created_at.desc(),
            ControlPlanVersion.major_no.desc(),
            ControlPlanVersion.minor_no.desc(),
            ControlPlanVersion.version_id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


def _latest_item_ids(latest_ver) -> set[str]:
    if latest_ver is None:
        return set()
    snap = latest_ver.items_snapshot
    items = snap.get("items", []) if isinstance(snap, dict) else (snap or [])
    return {str(i.get("item_id")) for i in items if i.get("item_id")}


async def scan_tenant_breaks(db: AsyncSession, tenant_schema: str) -> list[dict]:
    """Report blocked modify key_points for open CAPAs in this tenant.

    A break = current analysis has a cp_item modify key_point whose
    target_key (item_id) is NOT in the latest CP version snapshot. delete
    key_points whose target disappeared are NOT reported (expected outcome).
    """
    breaks: list[dict] = []
    # Open CAPAs only (D1–D8_APPROVAL_PENDING); terminal CAPAs skipped.
    open_capas = (await db.execute(
        select(CAPAEightD)
    )).scalars().all()
    open_capas = [c for c in open_capas if is_capa_open_value(c.status)]
    capa_ids = {c.report_id for c in open_capas}
    if not capa_ids:
        return breaks
    analyses = (await db.execute(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.is_current == True,
            CapaDocgAnalysis.capa_id.in_(capa_ids),
        )
    )).scalars().all()
    capa_by_id = {c.report_id: c for c in open_capas}
    for analysis in analyses:
        capa = capa_by_id.get(analysis.capa_id)
        if capa is None:
            continue
        if not analysis.affected_docs:
            continue
        for doc in analysis.affected_docs:
            if doc.get("doc_type") != "control_plan":
                continue
            try:
                cp_id = uuid.UUID(str(doc["doc_id"]))
            except (ValueError, TypeError):
                continue
            latest_ver = await _latest_cp_version(db, cp_id)
            if latest_ver is None:
                # No version yet — modify cannot be covered but this is a data
                # gap, not an item_id lineage break. Skip.
                continue
            latest_ids = _latest_item_ids(latest_ver)
            for kp in doc.get("key_points", []):
                if kp.get("expected_action") != "modify":
                    continue
                if kp.get("target_kind") != "cp_item":
                    continue
                tk = str(kp.get("target_key") or "")
                if tk and tk not in latest_ids:
                    breaks.append({
                        "tenant_schema": tenant_schema,
                        "capa_id": str(capa.report_id),
                        "capa_document_no": capa.document_no,
                        "capa_status": capa.status,
                        "cp_id": str(cp_id),
                        "latest_version_id": str(latest_ver.version_id),
                        "blocked_modify_target_key": tk,
                        "blocked_field": kp.get("field"),
                    })
    return breaks


async def run_preflight(json_output: bool = False) -> int:
    all_breaks: list[dict] = []
    async for tenant, db in run_for_each_tenant():
        all_breaks.extend(await scan_tenant_breaks(db, tenant.schema_name))
    if json_output:
        print(json.dumps({"breaks": all_breaks, "count": len(all_breaks)},
                         ensure_ascii=False, indent=2))
    elif not all_breaks:
        print("doc-gate CP lineage preflight: CLEAN (0 blocked modify key_points)")
    else:
        print(f"doc-gate CP lineage preflight: {len(all_breaks)} BLOCKED modify key_point(s) — "
              "deployment blocked, manual remediation required:")
        for b in all_breaks:
            print(f"  - tenant={b['tenant_schema']} CAPA {b['capa_document_no']} "
                  f"({b['capa_id']}, status={b['capa_status']})")
            print(f"      CP {b['cp_id']} latest v{b['latest_version_id']}: "
                  f"modify target_key={b['blocked_modify_target_key']} "
                  f"field={b['blocked_field']} absent from latest snapshot")
            print(f"      → this CAPA cannot pass the doc-gate modify check. "
                  f"Re-create the analysis AFTER confirming the CP item_id is "
                  f"preserved going forward (delete the stale current analysis).")
    return 1 if all_breaks else 0


def main() -> None:
    p = argparse.ArgumentParser(description="US-E2E-01.7 doc-gate CP lineage preflight")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = p.parse_args()
    rc = asyncio.run(run_preflight(json_output=args.json))
    sys.exit(rc)


if __name__ == "__main__":
    main()
