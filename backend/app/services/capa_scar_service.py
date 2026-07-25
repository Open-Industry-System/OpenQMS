"""CAPA → SCAR trigger (US-E2E-01.5)."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import re

from app.core.deps import RequestScope
from app.core.factory_scope import is_factory_visible, check_product_line_access
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_d3 import CapaD3ImpactReport, CapaD3ImportRun
from app.models.supplier import Supplier, SupplierSCAR
from app.services import scar_service

_BLOCKED_STATUSES = frozenset({"D1_TEAM", "D2_DESCRIPTION", "ARCHIVED"})
_DESC_MAX = 8000  # soft cap; align with practical Text size
# Match only the lot-summary line we emit; won't cull user prose mentioning 受影响批次
_LOT_LINE_RE = re.compile(r"^[ \t]*受影响批次\s*[:：]", re.MULTILINE)


async def load_capa_visible_or_404(
    db: AsyncSession, report_id: uuid.UUID, scope: RequestScope
) -> CAPAEightD:
    capa = await db.get(CAPAEightD, report_id)
    if capa is None or not is_factory_visible(capa.factory_id, scope):
        raise LookupError("8D report not found")
    return capa


async def load_d3_affected_lots(db: AsyncSession, capa_id: uuid.UUID) -> list[str]:
    """Current import run → current impact report → batches[].lot_no (non-empty, unique, order preserved)."""
    run = await db.scalar(
        select(CapaD3ImportRun).where(
            CapaD3ImportRun.capa_id == capa_id,
            CapaD3ImportRun.is_current == True,  # noqa: E712
        )
    )
    if run is None:
        return []
    report = await db.scalar(
        select(CapaD3ImpactReport).where(
            CapaD3ImpactReport.run_id == run.run_id,
            CapaD3ImpactReport.is_current == True,  # noqa: E712
        )
    )
    if report is None or not report.batches:
        return []
    lots: list[str] = []
    seen: set[str] = set()
    for batch in report.batches:
        if not isinstance(batch, dict):
            continue
        lot = batch.get("lot_no")
        if not lot or not str(lot).strip():
            continue
        lot_s = str(lot).strip()
        if lot_s in seen:
            continue
        seen.add(lot_s)
        lots.append(lot_s)
    return lots


def _strip_lot_lines(text: str) -> str:
    """Remove pre-existing lot-summary lines so lots are owned by `lots` param.

    Only matches lines of the form ``受影响批次: ...`` (the lot line we emit),
    so user prose like ``受影响批次分析结论：风险低`` is preserved.
    """
    return "\n".join(
        ln for ln in text.splitlines()
        if not _LOT_LINE_RE.match(ln)
    ).strip()


def build_scar_description(
    capa: CAPAEightD,
    *,
    body_description: str | None,
    lots: list[str],
) -> str:
    """Build SCAR description; lot line is derived solely from `lots`.

    Body description is the narrative base (any embedded 受影响批次 lines are
    stripped). Empty `lots` clears the lot surface (``affected_batches: []``);
    non-empty always appends a single lot line. Lot line is reserved inside the
    soft length cap so truncation cannot drop it.
    """
    if body_description and body_description.strip():
        text = _strip_lot_lines(body_description.strip())
    else:
        parts = [f"{capa.document_no} {capa.title}".strip()]
        if capa.d2_description:
            parts.append(f"[问题描述] {capa.d2_description}")
        if capa.d4_root_cause:
            parts.append(f"[根因] {capa.d4_root_cause}")
        text = "\n".join(parts)
    if lots:
        lot_line = "受影响批次: " + ", ".join(lots)
        # Reserve room for lot line (+ newline) so soft cap cannot drop it
        budget = max(0, _DESC_MAX - len(lot_line) - (1 if text else 0))
        text = text[:budget]
        text = f"{text}\n{lot_line}" if text else lot_line
        return text[:_DESC_MAX]
    return text[:_DESC_MAX]


async def trigger_scar_from_capa(
    db: AsyncSession,
    report_id: uuid.UUID,
    *,
    supplier_id: uuid.UUID,
    user_id: uuid.UUID,
    scope: RequestScope,
    description: str | None = None,
    requested_action: str | None = None,
    due_date: date | None = None,
    affected_batches: list[str] | None = None,
) -> SupplierSCAR:
    await load_capa_visible_or_404(db, report_id, scope)

    # FOR UPDATE + populate_existing so concurrent triggers see the bound scar_ref_id
    result = await db.execute(
        select(CAPAEightD)
        .where(CAPAEightD.report_id == report_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    capa = result.scalar_one()

    check_product_line_access(capa.product_line_code, scope)  # HTTPException 403

    if capa.status in _BLOCKED_STATUSES:
        raise ValueError(f"当前状态 {capa.status} 不允许发起 SCAR")
    if capa.scar_ref_id is not None:
        raise ValueError("该 8D 已关联 SCAR")

    supplier = await db.get(Supplier, supplier_id)
    if supplier is None:
        raise ValueError("供应商不存在")
    if supplier.factory_id != capa.factory_id:
        raise ValueError("供应商与 8D 必须同厂")

    if affected_batches is None:
        lots = await load_d3_affected_lots(db, capa.report_id)
    else:
        lots = list(affected_batches)

    desc = build_scar_description(capa, body_description=description, lots=lots)

    try:
        scar = await scar_service._create_scar_without_commit(
            db,
            supplier_id=supplier_id,
            source_type="capa",
            source_id=capa.report_id,
            description=desc,
            requested_action=requested_action,
            due_date=due_date,
            issued_by=user_id,
            product_line_code=capa.product_line_code,
            factory_id=capa.factory_id,
            capa_ref_id=capa.report_id,
        )
        capa.scar_ref_id = scar.scar_id
        db.add(
            AuditLog(
                table_name="capa_eightd",
                record_id=capa.report_id,
                action="SCAR_TRIGGERED",
                operated_by=user_id,
                factory_id=capa.factory_id,
                changed_fields={
                    "capa_id": str(capa.report_id),
                    "scar_id": str(scar.scar_id),
                    "scar_no": scar.scar_no,
                    "supplier_id": str(supplier_id),
                    "source_type": "capa",
                    "affected_batches": lots,
                },
            )
        )
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        err = str(getattr(e, "orig", e))
        if "uq_capa_eightd_scar_ref_id" in err or "uq_supplier_scars_capa_ref_id" in err:
            raise ValueError("该 8D 已关联 SCAR") from e
        raise

    return await scar_service.get_scar(db, scar.scar_id)
