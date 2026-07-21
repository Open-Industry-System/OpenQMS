from __future__ import annotations

import re
from dataclasses import dataclass, field

_WS = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    if not text:
        return ""
    return _WS.sub(" ", text.strip()).lower()


@dataclass
class PLHit:
    product_line_code: str
    product_type_code: str | None
    factory_id: str
    hit_criteria: list[str] = field(default_factory=list)
    evidence: dict[str, list[dict]] = field(default_factory=dict)


def aggregate_by_type(
    hits: list[dict], *, max_types: int = 50, max_pls_per_type: int = 30
) -> tuple[list[dict], bool]:
    """合并同 PL 命中、按 type 分组、稳定排序+截断。返回 (similar_products, truncated)。"""
    by_pl: dict[str, dict] = {}
    for h in hits:
        code = h["product_line_code"]
        cur = by_pl.get(code)
        if cur is None:
            cur = {
                "product_line_code": code,
                "product_type_code": h.get("product_type_code"),
                "factory_id": h["factory_id"],
                "hit_criteria": [],
                "evidence": {},
            }
            by_pl[code] = cur
        for c in h["hit_criteria"]:
            if c not in cur["hit_criteria"]:
                cur["hit_criteria"].append(c)
        for k, v in h.get("evidence", {}).items():
            cur["evidence"].setdefault(k, [])
            cur["evidence"][k].extend(v)

    # 按 type 分组
    groups: dict[str, list[dict]] = {}
    for pl in by_pl.values():
        type_code = pl["product_type_code"] or "unknown"
        groups.setdefault(type_code, []).append(pl)

    out: list[dict] = []
    for type_code in sorted(groups.keys()):
        full_pls = sorted(groups[type_code], key=lambda p: p["product_line_code"])
        pls = full_pls[:max_pls_per_type]
        out.append({
            "product_type_code": type_code,
            "product_type_name": "未分类" if type_code == "unknown" else type_code,
            "hit_criteria": sorted({c for p in pls for c in p["hit_criteria"]}),
            "suggestion_direction": None,  # LLM 填（Task 4）
            "product_lines": [
                {"code": p["product_line_code"], "factory_id": p["factory_id"]} for p in pls
            ],
            "evidence": {k: v for p in pls for k, v in p["evidence"].items()},
        })

    truncated = len(groups) > max_types or any(
        len(groups[type_code]) > max_pls_per_type for type_code in groups
    )
    out = out[:max_types]
    return out, truncated


# ─── DB matching (Task 3) ───────────────────────────────────────────────────

from dataclasses import dataclass  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.models.capa import CAPAEightD, CapaD7NodeAction  # noqa: E402
from app.models.product_line import ProductLine  # noqa: E402
from app.models.fmea import FMEADocument  # noqa: E402
from app.models.control_plan import ControlPlan, ControlPlanItem  # noqa: E402
from app.models.iqc_inspection import IqcInspection  # noqa: E402
from app.models.iqc_material import IqcMaterial  # noqa: E402
from app.models.capa_d3 import CapaD3ImportRun, CapaD3ImpactReport  # noqa: E402

APPROVED_FMEA_STATUSES = ("approved",)
APPROVED_CP_STATUSES = ("approved",)


@dataclass
class SourceSnapshot:
    source_pl: str
    source_factory_id: str
    source_type: str | None
    source_supplier_id: str | None
    fmea_mode_texts: set[str]
    cp_keys: set[str]
    material_codes: set[str]


def _cp_item_key(it: ControlPlanItem) -> str:
    return normalize(
        "|".join(
            filter(
                None,
                [
                    it.characteristic_no,
                    it.product_characteristic,
                    it.process_characteristic,
                    it.special_class,
                ],
            )
        )
    )


async def build_source_snapshot(db, capa: CAPAEightD) -> SourceSnapshot:
    src_pl_row = await db.scalar(
        select(ProductLine).where(ProductLine.code == capa.product_line_code)
    )
    source_type = src_pl_row.product_type_code if src_pl_row else None

    fmea_ids: set = set()
    if capa.fmea_ref_id:
        fmea_ids.add(capa.fmea_ref_id)
    rows = await db.execute(
        select(CapaD7NodeAction.fmea_id).where(
            CapaD7NodeAction.capa_id == capa.report_id,
            CapaD7NodeAction.action.in_(("confirmed", "auto_filled")),
            CapaD7NodeAction.fmea_id.is_not(None),
        )
    )
    for (fid,) in rows.all():
        fmea_ids.add(fid)

    fmea_mode_texts: set[str] = set()
    if fmea_ids:
        fmea_rows = await db.execute(
            select(FMEADocument).where(FMEADocument.fmea_id.in_(list(fmea_ids)))
        )
        for fm in fmea_rows.scalars().all():
            for n in (fm.graph_data or {}).get("nodes", []):
                if n.get("type") in ("FailureMode", "FailureCause"):
                    t = normalize(n.get("name"))
                    if t:
                        fmea_mode_texts.add(t)

    cp_keys: set[str] = set()
    cp_rows = await db.execute(
        select(ControlPlanItem)
        .join(ControlPlan, ControlPlan.cp_id == ControlPlanItem.cp_id)
        .where(
            ControlPlan.product_line_code == capa.product_line_code,
            ControlPlan.status.in_(APPROVED_CP_STATUSES),
        )
    )
    for it in cp_rows.scalars().all():
        key = _cp_item_key(it)
        if key:
            cp_keys.add(key)

    material_codes: set[str] = set()
    run = await db.scalar(
        select(CapaD3ImportRun).where(
            CapaD3ImportRun.capa_id == capa.report_id,
            CapaD3ImportRun.factory_id == capa.factory_id,
            CapaD3ImportRun.is_current.is_(True),
        )
    )
    if run:
        rpt = await db.scalar(
            select(CapaD3ImpactReport).where(
                CapaD3ImpactReport.run_id == run.run_id,
                CapaD3ImpactReport.is_current.is_(True),
                CapaD3ImpactReport.status == "done",
            )
        )
        if rpt and rpt.batches:
            for b in rpt.batches:
                m = normalize(b.get("material_code") if isinstance(b, dict) else None)
                if m:
                    material_codes.add(m)

    return SourceSnapshot(
        source_pl=capa.product_line_code,
        source_factory_id=str(capa.factory_id),
        source_type=source_type,
        source_supplier_id=str(capa.supplier_id) if capa.supplier_id else None,
        fmea_mode_texts=fmea_mode_texts,
        cp_keys=cp_keys,
        material_codes=material_codes,
    )


async def match_criteria(db, snap: SourceSnapshot) -> list[dict]:
    hits: dict[str, dict] = {}

    def _ensure(code, type_code, factory_id):
        if code not in hits:
            hits[code] = {
                "product_line_code": code,
                "product_type_code": type_code,
                "factory_id": factory_id,
                "hit_criteria": [],
                "evidence": {},
            }
        return hits[code]

    pl_rows = (
        await db.execute(
            select(ProductLine).where(
                ProductLine.is_active.is_(True),
                ProductLine.code != snap.source_pl,
            )
        )
    ).scalars().all()
    pl_by_code = {p.code: p for p in pl_rows}

    # 依据 1: same product type
    if snap.source_type:
        for p in pl_rows:
            if p.product_type_code == snap.source_type:
                _ensure(p.code, p.product_type_code, str(p.factory_id))[
                    "hit_criteria"
                ].append("same_product_type")

    # 依据 2: shared FMEA FailureMode/Cause name
    if snap.fmea_mode_texts:
        fm_rows = (
            await db.execute(
                select(FMEADocument).where(
                    FMEADocument.status.in_(APPROVED_FMEA_STATUSES),
                    FMEADocument.product_line_code != snap.source_pl,
                )
            )
        ).scalars().all()
        for fm in fm_rows:
            for n in (fm.graph_data or {}).get("nodes", []):
                if n.get("type") in ("FailureMode", "FailureCause"):
                    t = normalize(n.get("name"))
                    if t and t in snap.fmea_mode_texts:
                        p = pl_by_code.get(fm.product_line_code)
                        if p:
                            h = _ensure(p.code, p.product_type_code, str(p.factory_id))
                            if "shared_fmea_mode" not in h["hit_criteria"]:
                                h["hit_criteria"].append("shared_fmea_mode")
                            h["evidence"].setdefault("shared_fmea_mode", []).append(
                                {
                                    "fmea_id": str(fm.fmea_id),
                                    "node_id": n.get("id"),
                                    "node_type": n.get("type"),
                                    "matched_text": t,
                                }
                            )

    # 依据 3: shared control plan characteristic key
    if snap.cp_keys:
        cp_rows = (
            await db.execute(
                select(ControlPlanItem, ControlPlan).where(
                    ControlPlan.cp_id == ControlPlanItem.cp_id,
                    ControlPlan.status.in_(APPROVED_CP_STATUSES),
                    ControlPlan.product_line_code != snap.source_pl,
                )
            )
        ).all()
        for it, cp in cp_rows:
            key = _cp_item_key(it)
            if key and key in snap.cp_keys:
                p = pl_by_code.get(cp.product_line_code)
                if p:
                    h = _ensure(p.code, p.product_type_code, str(p.factory_id))
                    if "shared_control_plan" not in h["hit_criteria"]:
                        h["hit_criteria"].append("shared_control_plan")
                    h["evidence"].setdefault("shared_control_plan", []).append(
                        {"cp_id": str(cp.cp_id), "characteristic_keys": [key]}
                    )

    # 依据 4: same supplier + material (A ∪ B)
    if snap.source_supplier_id and snap.material_codes:
        from uuid import UUID as _UUID

        try:
            supplier_uuid = _UUID(snap.source_supplier_id)
        except ValueError:
            supplier_uuid = None
        if supplier_uuid is not None:
            insp_rows = (
                await db.execute(
                    select(IqcInspection).where(
                        IqcInspection.supplier_id == supplier_uuid,
                        IqcInspection.product_line_code.is_not(None),
                        IqcInspection.product_line_code != snap.source_pl,
                    )
                )
            ).scalars().all()
            for ins in insp_rows:
                m = normalize(ins.part_no)
                if m and m in snap.material_codes:
                    p = pl_by_code.get(ins.product_line_code)
                    if p:
                        h = _ensure(p.code, p.product_type_code, str(p.factory_id))
                        if "same_supplier_material" not in h["hit_criteria"]:
                            h["hit_criteria"].append("same_supplier_material")
                        h["evidence"].setdefault("same_supplier_material", []).append(
                            {
                                "supplier_id": snap.source_supplier_id,
                                "material_code": m,
                            }
                        )

            mat_rows = (
                await db.execute(
                    select(IqcMaterial).where(
                        IqcMaterial.status == "active",
                        IqcMaterial.product_line_code != snap.source_pl,
                    )
                )
            ).scalars().all()
            for mat in mat_rows:
                m = normalize(mat.part_no)
                if not (m and m in snap.material_codes):
                    continue
                bound = await db.scalar(
                    select(IqcInspection).where(
                        IqcInspection.material_id == mat.material_id,
                        IqcInspection.supplier_id == supplier_uuid,
                    )
                )
                if bound:
                    p = pl_by_code.get(mat.product_line_code)
                    if p:
                        h = _ensure(p.code, p.product_type_code, str(p.factory_id))
                        if "same_supplier_material" not in h["hit_criteria"]:
                            h["hit_criteria"].append("same_supplier_material")
                        h["evidence"].setdefault("same_supplier_material", []).append(
                            {
                                "supplier_id": snap.source_supplier_id,
                                "material_code": m,
                            }
                        )

    return list(hits.values())


# ─── close-path check + LLM (Task 4) ────────────────────────────────────────

import json as _json
import uuid as _uuid

from app.models.audit import AuditLog
from app.models.capa_lateral_diffusion import CapaLateralDiffusionCheck
from app.services.agent.provider_adapter import (
    ProviderNotConfiguredError,
    build_client,
    complete_json,
)

LATERAL_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_type_code": {"type": "string"},
                    "suggestion_direction": {"type": "string"},
                },
                "required": ["product_type_code", "suggestion_direction"],
            },
        }
    },
    "required": ["items"],
}


class LateralBlockedError(RuntimeError):
    """有命中但无 LLM 凭证。"""


class LateralFailedError(RuntimeError):
    """确定性匹配异常或 LLM 失败。"""


def _check_id_for(capa_id) -> _uuid.UUID:
    return _uuid.uuid5(_uuid.NAMESPACE_URL, f"lateral_check:capa:{capa_id}")


def _build_prompt(capa, similar) -> str:
    return (
        f"8D 报告 {capa.document_no}（严重度 {capa.severity}）已关闭。\n"
        f"D2: {capa.d2_description or ''}\nD4 根因: {capa.d4_root_cause or ''}\n"
        f"命中类似产品类型:\n{_json.dumps([{'product_type_code': s['product_type_code'], 'hit_criteria': s['hit_criteria']} for s in similar], ensure_ascii=False)}\n"
        "为每个 product_type_code 生成 suggestion_direction（建议相关产品负责人更新方向，中文，≤120字）。"
    )


async def run_lateral_diffusion_check(db, capa, user_id) -> None:
    """D8 close-path fail-closed lateral check. Empty hits skip LLM; hits require LLM."""
    try:
        snap = await build_source_snapshot(db, capa)
        hits = await match_criteria(db, snap)
    except Exception as e:
        raise LateralFailedError(f"lateral matching failed: {e}") from e

    similar, truncated = aggregate_by_type(hits)
    status = "done" if similar else "empty"

    if similar:
        try:
            pc = await build_client(db)
        except ProviderNotConfiguredError as e:
            raise LateralBlockedError(f"LLM not configured: {e}") from e
        try:
            result = await complete_json(pc, _build_prompt(capa, similar), LATERAL_SCHEMA)
        except Exception as e:
            raise LateralFailedError(f"LLM call failed: {e}") from e
        if not isinstance(result, dict):
            raise LateralFailedError("LLM returned non-object")
        by_type = {
            it["product_type_code"]: it["suggestion_direction"]
            for it in result.get("items", [])
            if isinstance(it, dict) and "product_type_code" in it
        }
        missing = [
            sp["product_type_code"] for sp in similar if sp["product_type_code"] not in by_type
        ]
        if missing:
            raise LateralFailedError(f"LLM missing suggestions for: {missing}")
        for sp in similar:
            sp["suggestion_direction"] = by_type[sp["product_type_code"]]
        llm_status = "done"
    else:
        llm_status = "skipped"

    check_id = _check_id_for(capa.report_id)
    existing = await db.get(CapaLateralDiffusionCheck, check_id)
    if existing:
        existing.source_product_line_code = snap.source_pl
        existing.source_product_type_code = snap.source_type
        existing.similar_products = similar
        existing.status = status
        existing.llm_status = llm_status
        existing.truncated = truncated
    else:
        db.add(
            CapaLateralDiffusionCheck(
                check_id=check_id,
                capa_id=capa.report_id,
                factory_id=capa.factory_id,
                source_product_line_code=snap.source_pl,
                source_product_type_code=snap.source_type,
                similar_products=similar,
                status=status,
                llm_status=llm_status,
                truncated=truncated,
            )
        )

    db.add(
        AuditLog(
            table_name="capa_eightd",
            record_id=capa.report_id,
            action="LATERAL_DIFFUSION_CHECKED",
            changed_fields={
                "check_id": str(check_id),
                "similar_count": len(similar),
                "status": status,
                "truncated": truncated,
                "product_type_codes": [sp["product_type_code"] for sp in similar],
                "hit_criteria_union": sorted(
                    {c for sp in similar for c in sp["hit_criteria"]}
                ),
            },
            operated_by=user_id,
            factory_id=capa.factory_id,
            correlation_id=_uuid.uuid5(
                _uuid.NAMESPACE_URL, f"lateral_check:{capa.report_id}"
            ),
        )
    )
