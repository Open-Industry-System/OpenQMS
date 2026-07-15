"""Preflight: detect CP item_id lineage breaks that block the D8 doc-gate.

US-E2E-01.7 contract v2 uses item_id as the stable target_key for CP modify/
delete coverage.

Two scan modes (both over open CAPAs only, all active tenant schemas):

1. **With current analysis** — for each cp_item modify key_point, check that
   target_key exists in the latest CP version (via get_latest_cp_version).
   delete targets that disappeared are NOT reported (expected outcome).

2. **Without analysis (pre-generation)** — for each open CAPA, scan candidate
   CPs (same factory_id + product_line_code). If the CAPA-time baseline version
   (created_at <= capa.created_at) has a non-empty item_id set with ZERO
   overlap against latest, report a potential break (any future modify on
   those baseline ids would fail).

Exit code: 1 if any break found (blocks `make check` / deploy), 0 otherwise.

Usage:
    python -m app.services.capa_doc_gate_preflight
    python -m app.services.capa_doc_gate_preflight --json
    make doc-gate-preflight
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

    # Mode 1: current analyses — precise modify key_point checks
    analyses = (await db.execute(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.is_current == True,  # noqa: E712
            CapaDocgAnalysis.capa_id.in_(capa_ids),
        )
    )).scalars().all()
    analyzed_capa_ids: set[uuid.UUID] = set()
    for analysis in analyses:
        capa = capa_by_id.get(analysis.capa_id)
        if capa is None:
            continue
        analyzed_capa_ids.add(capa.report_id)
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
            latest_ids = _item_ids_from_snapshot(latest_ver.items_snapshot)
            for kp in doc.get("key_points") or []:
                if not isinstance(kp, dict):
                    continue
                if kp.get("expected_action") != "modify" or kp.get("target_kind") != "cp_item":
                    continue
                tk = str(kp.get("target_key") or "").strip()
                if tk and tk not in latest_ids:
                    breaks.append({
                        "kind": "blocked_modify",
                        "tenant_schema": tenant_schema,
                        "capa_id": str(capa.report_id),
                        "capa_document_no": capa.document_no,
                        "capa_status": capa.status,
                        "cp_id": str(cp_id),
                        "latest_version_id": str(latest_ver.version_id),
                        "blocked_modify_target_key": tk,
                        "blocked_field": kp.get("field"),
                    })

    # Mode 2: open CAPAs without current analysis — candidate CP full disconnect
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


async def run_preflight(json_output: bool = False) -> int:
    all_breaks: list[dict] = []
    async for tenant, db in run_for_each_tenant():
        all_breaks.extend(await scan_tenant_breaks(db, tenant.schema_name))
    if json_output:
        print(json.dumps({"breaks": all_breaks, "count": len(all_breaks)},
                         ensure_ascii=False, indent=2))
    elif not all_breaks:
        print("doc-gate CP lineage preflight: CLEAN (0 breaks)")
    else:
        print(f"doc-gate CP lineage preflight: {len(all_breaks)} break(s) — "
              "deployment blocked, manual remediation required:")
        for b in all_breaks:
            if b["kind"] == "blocked_modify":
                print(f"  - [{b['tenant_schema']}] CAPA {b['capa_document_no']} "
                      f"({b['capa_id']}, {b['capa_status']})")
                print(f"      CP {b['cp_id']}: modify target_key={b['blocked_modify_target_key']} "
                      f"field={b['blocked_field']} absent from latest v{b['latest_version_id']}")
                print("      → cannot pass doc-gate. Demote/delete the stale current analysis; "
                      "re-author CP under the item_id-preserving save path, then regenerate analysis.")
            else:
                print(f"  - [{b['tenant_schema']}] CAPA {b['capa_document_no']} "
                      f"({b['capa_id']}, {b['capa_status']}) [no analysis yet]")
                print(f"      CP {b['cp_id']}: baseline item_ids share NONE with latest "
                      f"(baseline={b['baseline_version_id']}, latest={b['latest_version_id']})")
                print("      → any future modify key_point on baseline ids will fail. "
                      "Re-save CP (item_id-preserving) so a new latest version continues "
                      "current ids, or accept that only delete/add/document paths can pass.")
    return 1 if all_breaks else 0


def main() -> None:
    p = argparse.ArgumentParser(description="US-E2E-01.7 doc-gate CP lineage preflight")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = p.parse_args()
    rc = asyncio.run(run_preflight(json_output=args.json))
    sys.exit(rc)


if __name__ == "__main__":
    main()
