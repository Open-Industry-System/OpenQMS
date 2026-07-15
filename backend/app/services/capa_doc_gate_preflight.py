"""Preflight scan: detect CP item_id lineage breaks that block the D8 doc-gate.

US-E2E-01.7 contract v2 uses item_id as the stable target_key for CP modify/
delete coverage. Historical CP versions created by the old whole-table UUID
rebuild logic have no item_id continuity with later versions, so a CAPA whose
baseline is such an old version can never satisfy a modify key_point against
the current latest (the baseline id is absent from the latest snapshot).

This module scans all current CAPA doc-gate analyses + baseline CP versions
and reports any (capa, doc) pair where baseline item_ids are entirely absent
from the latest version. Such pairs require manual remediation BEFORE the
contract-v2 doc-gate is usable for that CAPA (re-run audit will always block).

Usage:
    python -m app.services.capa_doc_gate_preflight                # exit 0 clean / 1 breaks
    python -m app.services.capa_doc_gate_preflight --json          # machine-readable
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.capa import CAPAEightD
from app.models.capa_doc_gate import CapaDocgAnalysis
from app.models.control_plan_version import ControlPlanVersion


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


async def scan_cp_lineage_breaks(db: AsyncSession) -> list[dict]:
    """Return list of {capa_id, capa_document_no, cp_id, baseline_ids, latest_ids}.

    A break = baseline CP version item_ids have ZERO overlap with latest version
    item_ids (both non-empty). Such CAPAs cannot pass a CP modify key_point.
    """
    breaks: list[dict] = []
    # Find current analyses that include a control_plan affected doc
    analyses = (await db.execute(
        select(CapaDocgAnalysis).where(CapaDocgAnalysis.is_current == True)
    )).scalars().all()
    for analysis in analyses:
        if not analysis.affected_docs:
            continue
        capa = await db.get(CAPAEightD, analysis.capa_id)
        if capa is None:
            continue
        for doc in analysis.affected_docs:
            if doc.get("doc_type") != "control_plan":
                continue
            try:
                cp_id = uuid.UUID(str(doc["doc_id"]))
            except (ValueError, TypeError):
                continue
            baseline_ver_id = doc.get("baseline_version_id")
            if not baseline_ver_id:
                continue  # new doc, no baseline to break
            baseline_ver = await db.get(ControlPlanVersion, uuid.UUID(str(baseline_ver_id)))
            latest_ver = await _latest_cp_version(db, cp_id)
            if baseline_ver is None or latest_ver is None:
                continue
            b_snap = baseline_ver.items_snapshot
            b_items = b_snap.get("items", []) if isinstance(b_snap, dict) else (b_snap or [])
            l_snap = latest_ver.items_snapshot
            l_items = l_snap.get("items", []) if isinstance(l_snap, dict) else (l_snap or [])
            b_ids = {str(i.get("item_id")) for i in b_items if i.get("item_id")}
            l_ids = {str(i.get("item_id")) for i in l_items if i.get("item_id")}
            if b_ids and l_ids and not (b_ids & l_ids):
                breaks.append({
                    "capa_id": str(capa.report_id),
                    "capa_document_no": capa.document_no,
                    "cp_id": str(cp_id),
                    "baseline_version_id": str(baseline_ver.version_id),
                    "latest_version_id": str(latest_ver.version_id),
                    "baseline_item_ids": sorted(b_ids),
                    "latest_item_ids": sorted(l_ids),
                })
    return breaks


async def run_preflight(json_output: bool = False) -> int:
    async with async_session() as db:
        breaks = await scan_cp_lineage_breaks(db)
    if json_output:
        print(json.dumps({"breaks": breaks, "count": len(breaks)}, ensure_ascii=False, indent=2))
    else:
        if not breaks:
            print("doc-gate CP lineage preflight: CLEAN (0 breaks)")
        else:
            print(f"doc-gate CP lineage preflight: {len(breaks)} BREAK(S) — manual remediation required:")
            for b in breaks:
                print(f"  - CAPA {b['capa_document_no']} ({b['capa_id']})")
                print(f"      CP {b['cp_id']}: baseline v{b['baseline_version_id']} ids "
                      f"{b['baseline_item_ids']} share NONE with latest v{b['latest_version_id']} ids")
                print(f"      → regenerate doc-gate analysis after confirming CP identity; "
                      f"old baseline modify key_points cannot be satisfied")
    return 1 if breaks else 0


def main() -> None:
    p = argparse.ArgumentParser(description="US-E2E-01.7 doc-gate CP lineage preflight")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = p.parse_args()
    rc = asyncio.run(run_preflight(json_output=args.json))
    sys.exit(rc)


if __name__ == "__main__":
    main()
