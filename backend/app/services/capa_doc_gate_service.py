"""US-E2E-01.7 D8 doc update gate service. Mirrors capa_d3_containment_service three-phase pattern."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision
from app.models.capa import CAPAEightD
from app.models.audit import AuditLog
from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import ProviderClient, ProviderNotConfiguredError
from app.services.version_service import get_latest_cp_version, get_latest_fmea_version

logger = logging.getLogger(__name__)
STALE_THRESHOLD_SECONDS = 300  # 5 min; running older than 2x = stale
RETRY_AFTER_SECONDS = 2
_ALLOWED_NODE_TYPES = {"FailureMode", "FailureEffect", "FailureCause", "ProcessStep", "Function", "WorkElement"}


async def generate_impact_analysis(db: AsyncSession, capa: CAPAEightD, user_id: uuid.UUID) -> dict:
    """Three-phase: phase1 lock+demote+stale-recovery+running+commit; phase2 LLM; phase3 CAS."""
    p1 = await _phase1_create_running(db, capa, user_id)
    if p1["status"] in ("blocked", "failed", "running", "superseded"):
        return p1
    phase2 = await _phase2_llm(db, capa, p1)
    return await _phase3_cas(db, capa, p1, phase2, user_id)


async def get_latest_analysis(db: AsyncSession, capa: CAPAEightD) -> dict | None:
    """Return latest analysis (incl failed) for this capa. ORDER BY created_at DESC, analysis_id DESC."""
    row = await db.scalar(
        select(CapaDocgAnalysis).where(CapaDocgAnalysis.capa_id == capa.report_id)
        .order_by(CapaDocgAnalysis.created_at.desc(), CapaDocgAnalysis.analysis_id.desc()).limit(1)
    )
    if row is None:
        return None
    return {"analysis_id": str(row.analysis_id), "status": row.status, "affected_docs": row.affected_docs,
            "error": row.error, "is_current": row.is_current}


# ---------------------------------------------------------------------------
# Phase 1: lock + demote old current + stale recovery + credential check + running + commit
# ---------------------------------------------------------------------------

async def _phase1_create_running(db: AsyncSession, capa: CAPAEightD, user_id: uuid.UUID) -> dict:
    # Lock capa row
    await db.execute(
        text("SELECT 1 FROM capa_eightd WHERE report_id=:cid FOR UPDATE"),
        {"cid": capa.report_id},
    )
    # Demote old current (fail-closed: before credential check)
    await db.execute(
        update(CapaDocgAnalysis)
        .where(CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.is_current == True)
        .values(is_current=False)
    )
    # Stale recovery: CAS running older than 2x threshold -> failed
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS * 2)
    await db.execute(
        update(CapaDocgAnalysis)
        .where(CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.status == "running",
               CapaDocgAnalysis.started_at < cutoff)
        .values(status="failed", error="stale", completed_at=datetime.now(timezone.utc))
    )
    # Existing running -> return retry_after
    existing = await db.scalar(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.status == "running"
        )
    )
    if existing:
        return {"status": "running", "analysis_id": str(existing.analysis_id),
                "retry_after": RETRY_AFTER_SECONDS}
    # Credential check
    try:
        client = await provider_adapter.build_client(db)
    except ProviderNotConfiguredError:
        now = datetime.now(timezone.utc)
        failed = CapaDocgAnalysis(
            analysis_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=capa.factory_id,
            is_current=False, status="failed", error="LLM 未配置", llm_available=False,
            completed_at=now, generated_by=user_id,
        )
        db.add(failed)
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id, action="DOC_IMPACT_ANALYZED",
            changed_fields={
                "status": "failed", "error": "LLM 未配置",
                "llm_available": False, "affected_doc_count": 0,
            },
            operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
        ))
        await db.commit()
        raise ValueError("BLOCKED: 无 LLM 凭证")
    # Create running
    attempt_token = uuid.uuid4()
    analysis = CapaDocgAnalysis(
        analysis_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=capa.factory_id,
        is_current=False, status="running", attempt_token=attempt_token,
        llm_available=False, generated_by=user_id,
    )
    db.add(analysis)
    await db.flush()
    await db.commit()
    return {"status": "phase1_done", "analysis_id": str(analysis.analysis_id),
            "attempt_token": attempt_token, "client": client}


# ---------------------------------------------------------------------------
# Phase 2: query candidates + pure dict + commit read txn + LLM (no txn)
# ---------------------------------------------------------------------------

async def _phase2_llm(db: AsyncSession, capa: CAPAEightD, p1: dict) -> dict:
    candidates = await _build_allowlist(db, capa)
    input_hash = _compute_input_hash(capa, candidates)
    prompt = _build_prompt(capa, candidates)
    # Commit any autobegun read txn before calling LLM
    await db.commit()
    pc = p1["client"]
    try:
        raw = await provider_adapter.complete_json(pc, prompt, _RESPONSE_SCHEMA)
    except Exception as e:
        return {"llm_error": str(e)}
    # complete_json may return non-dict (array/null) if provider ignores schema —
    # convert to llm_error so phase3 CAS marks failed instead of leaving running.
    if not isinstance(raw, dict):
        return {"llm_error": f"LLM 输出非对象: {type(raw).__name__}"}
    raw["model"] = getattr(pc, "model", "unknown")
    raw["_input_hash"] = input_hash
    raw["_candidates"] = candidates
    return raw


# ---------------------------------------------------------------------------
# Phase 3: re-lock + C9 recheck + validate + unified CAS
# ---------------------------------------------------------------------------

async def _phase3_cas(db: AsyncSession, capa: CAPAEightD, p1: dict, phase2: dict, user_id: uuid.UUID) -> dict:
    analysis_id = uuid.UUID(p1["analysis_id"])
    attempt_token = p1["attempt_token"]
    now = datetime.now(timezone.utc)
    # LLM error -> CAS failed
    if "llm_error" in phase2:
        res = await db.execute(
            update(CapaDocgAnalysis)
            .where(CapaDocgAnalysis.analysis_id == analysis_id,
                   CapaDocgAnalysis.attempt_token == attempt_token, CapaDocgAnalysis.status == "running")
            .values(status="failed", error=phase2["llm_error"], completed_at=now)
        )
        if res.rowcount > 0:
            db.add(AuditLog(
                table_name="capa_eightd", record_id=capa.report_id, action="DOC_IMPACT_ANALYZED",
                changed_fields={
                    "status": "failed", "error": phase2["llm_error"],
                    "llm_available": True, "affected_doc_count": 0,
                },
                operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
            ))
            await db.commit()
            return {"status": "failed"}
        await db.commit()
        return {"status": "superseded"}
    # Re-lock + refresh capa + rebuild candidates (review P1#6: phase2's capa/candidates
    # are stale — captured before the LLM call. Must re-read to detect input changes
    # made during the LLM window.)
    await db.execute(text("SELECT 1 FROM capa_eightd WHERE report_id=:cid FOR UPDATE"), {"cid": capa.report_id})
    await db.refresh(capa)
    candidates = await _build_allowlist(db, capa)
    cur_hash = _compute_input_hash(capa, candidates)
    if cur_hash != phase2["_input_hash"]:
        res = await db.execute(
            update(CapaDocgAnalysis)
            .where(CapaDocgAnalysis.analysis_id == analysis_id,
                   CapaDocgAnalysis.attempt_token == attempt_token, CapaDocgAnalysis.status == "running")
            .values(status="failed", error="input_changed", completed_at=now)
        )
        if res.rowcount > 0:
            db.add(AuditLog(
                table_name="capa_eightd", record_id=capa.report_id, action="DOC_IMPACT_ANALYZED",
                changed_fields={
                    "status": "failed", "error": "input_changed",
                    "llm_available": True, "affected_doc_count": 0,
                },
                operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
            ))
            await db.commit()
            return {"status": "failed", "error": "input_changed"}
        await db.commit()
        return {"status": "superseded"}
    # Validate LLM output (C7 + vacuous pass + allowlist + discriminant union)
    affected = _validate_and_backfill(phase2, candidates)
    if isinstance(affected, str):  # error
        res = await db.execute(
            update(CapaDocgAnalysis)
            .where(CapaDocgAnalysis.analysis_id == analysis_id,
                   CapaDocgAnalysis.attempt_token == attempt_token, CapaDocgAnalysis.status == "running")
            .values(status="failed", error=affected, completed_at=now)
        )
        if res.rowcount > 0:
            db.add(AuditLog(
                table_name="capa_eightd", record_id=capa.report_id, action="DOC_IMPACT_ANALYZED",
                changed_fields={
                    "status": "failed", "error": affected,
                    "llm_available": True, "affected_doc_count": 0,
                },
                operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
            ))
            await db.commit()
            return {"status": "failed"}
        await db.commit()
        return {"status": "superseded"}
    # CAS promote to done
    res = await db.execute(
        update(CapaDocgAnalysis)
        .where(CapaDocgAnalysis.analysis_id == analysis_id,
               CapaDocgAnalysis.attempt_token == attempt_token, CapaDocgAnalysis.status == "running")
        .values(status="done", is_current=True, affected_docs=affected,
                analysis_input_hash=phase2["_input_hash"], llm_available=True,
                model=phase2.get("model"), completed_at=now)
    )
    if res.rowcount == 0:
        return {"status": "superseded"}
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id, action="DOC_IMPACT_ANALYZED",
        changed_fields={"affected_doc_count": len(affected), "llm_available": True, "status": "done"},
        operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
    ))
    await db.commit()
    return {"status": "done", "analysis_id": str(analysis_id)}


# ---------------------------------------------------------------------------
# Helpers: allowlist, hash, prompt, validation
# ---------------------------------------------------------------------------

def _cp_item_id(item: dict) -> str:
    return str(item.get("item_id") or "").strip()


async def _get_baseline_version(db: AsyncSession, doc_id: uuid.UUID, capa_created_at, doc_type: str):
    """Baseline = last version with created_at <= capa.created_at (NOT the overall latest).
    Deterministic tiebreak: created_at DESC, major_no DESC, minor_no DESC, version_id DESC.
    Returns None if no version exists at/before capa creation (new document after CAPA)."""
    from app.models.control_plan_version import ControlPlanVersion
    from app.models.fmea_version import FMEAVersion
    model = ControlPlanVersion if doc_type == "control_plan" else FMEAVersion
    parent_col = model.cp_id if doc_type == "control_plan" else model.fmea_id
    result = await db.execute(
        select(model).where(
            parent_col == doc_id,
            model.created_at <= capa_created_at,
        ).order_by(
            model.created_at.desc(), model.major_no.desc(), model.minor_no.desc(), model.version_id.desc()
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _build_allowlist(db: AsyncSession, capa: CAPAEightD) -> list[dict]:
    """Build doc candidates filtered by factory_id + product_line_code.
    Each entry: {doc_type, doc_id, doc_name, baseline_version_id, baseline_version, existing_targets, add_anchors}.
    """
    from app.models.fmea import FMEADocument
    from app.models.control_plan import ControlPlan
    from app.models.control_plan_version import ControlPlanVersion
    from app.models.fmea_version import FMEAVersion

    candidates = []
    pl = capa.product_line_code
    fid = capa.factory_id

    # CP candidates
    cp_result = await db.execute(
        select(ControlPlan).where(
            ControlPlan.factory_id == fid,
            ControlPlan.product_line_code == pl,
        )
    )
    for cp in cp_result.scalars().all():
        baseline = await _get_baseline_version(db, cp.cp_id, capa.created_at, "control_plan")
        cand = _cand_from_cp(cp, baseline)
        candidates.append(cand)

    # FMEA candidates
    fmea_result = await db.execute(
        select(FMEADocument).where(
            FMEADocument.factory_id == fid,
            FMEADocument.product_line_code == pl,
        )
    )
    for fmea in fmea_result.scalars().all():
        baseline = await _get_baseline_version(db, fmea.fmea_id, capa.created_at, "fmea")
        cand = _cand_from_fmea(fmea, baseline)
        candidates.append(cand)

    return candidates


def _cand_from_cp(cp, baseline) -> dict:
    cp_id = cp.cp_id if hasattr(cp, 'cp_id') else uuid.uuid4()
    cand = {
        "doc_type": "control_plan",
        "doc_id": str(cp_id),
        "doc_name": getattr(cp, "title", "CP"),
        "baseline_version_id": None,
        "baseline_version": None,
        "existing_targets": [],
        "add_anchors": [],
    }
    if baseline is not None:
        cand["baseline_version_id"] = str(baseline.version_id)
        items = baseline.items_snapshot.get("items", []) if isinstance(baseline.items_snapshot, dict) else baseline.items_snapshot or []
        cand["baseline_version"] = {"major": baseline.major_no, "minor": baseline.minor_no, "sha256": baseline.sha256_hash}
        # item_id is the stable unique target_key for existing CP items (immutable
        # within a version; CP save preserves it). product/process may be modified
        # without changing identity.
        cand["existing_targets"] = [
            {
                "target_kind": "cp_item",
                "target_key": _cp_item_id(i),
                "allowed_fields": [
                    "control_method", "reaction_plan", "special_class",
                    "sample_size", "sample_frequency",
                    "product_characteristic", "process_characteristic",
                ],
            }
            for i in items if _cp_item_id(i)
        ]
        known_fmea_ids = list({str(i.get("source_fmea_node_id", "")).strip() for i in items if i.get("source_fmea_node_id")})
        cand["add_anchors"] = [
            {"parent_node_id": nid, "node_type": "FailureMode"}
            for nid in known_fmea_ids if nid
        ]
    return cand


def _cand_from_fmea(fmea, baseline) -> dict:
    fid = fmea.fmea_id if hasattr(fmea, 'fmea_id') else uuid.uuid4()
    cand = {
        "doc_type": "fmea",
        "doc_id": str(fid),
        "doc_name": getattr(fmea, "title", "FMEA"),
        "baseline_version_id": None,
        "baseline_version": None,
        "existing_targets": [],
        "add_anchors": [],
    }
    if baseline is not None:
        cand["baseline_version_id"] = str(baseline.version_id)
        snapshot = baseline.snapshot or {}
        nodes = snapshot.get("nodes", [])
        edges = snapshot.get("edges", [])
        cand["baseline_version"] = {"major": baseline.major_no, "minor": baseline.minor_no, "sha256": baseline.sha256_hash}
        cand["existing_targets"] = [
            {"target_kind": "fmea_node", "target_key": n["id"], "allowed_fields": ["prevention_control", "detection_control", "name"]}
            for n in nodes if "id" in n
        ]
        # add_anchors: existing node IDs as valid parents
        existing_ids = [n["id"] for n in nodes if "id" in n]
        for nid in existing_ids:
            for nt in ("FailureMode", "FailureEffect", "FailureCause"):
                cand["add_anchors"].append({"parent_node_id": nid, "node_type": nt})
    return cand


# Bump when target_key / allowlist contract changes so old current analyses
# fail C9 and must be regenerated (no silent miss on re-audit).
DOC_GATE_CONTRACT_VERSION = 2


def _compute_input_hash(capa: CAPAEightD, candidates: list[dict]) -> str:
    """C9 hash: capa semantic input + candidate identity set (doc_type, doc_id) + baseline.
    MUST NOT include latest version (review P0#1 third round).
    Includes DOC_GATE_CONTRACT_VERSION so target-key contract upgrades invalidate
    stale current analyses (e.g. source_fmea_node_id → item_id).
    """
    payload = {
        "contract_version": DOC_GATE_CONTRACT_VERSION,
        "factory_id": str(capa.factory_id),
        "product_line_code": capa.product_line_code,
        "d4_root_cause": capa.d4_root_cause or "",
        "d5_correction": capa.d5_correction or "",
        "d7_prevention": capa.d7_prevention or "",
        "severity": capa.severity or "",
        "fmea_ref_id": str(capa.fmea_ref_id) if capa.fmea_ref_id else "",
        "fmea_node_id": capa.fmea_node_id or "",
        "candidates": sorted(
            (c["doc_type"], c["doc_id"], c.get("baseline_version_id") or "",
             (c.get("baseline_version") or {}).get("sha256", ""))
            for c in candidates
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _build_prompt(capa: CAPAEightD, candidates: list[dict]) -> str:
    """Build LLM prompt with doc allowlist + per-doc target allowlist + add_anchors."""
    doc_lines = []
    for c in candidates:
        line = f"- {c['doc_type']} id={c['doc_id']} name={c['doc_name']}"
        if c.get("baseline_version"):
            line += f" (v{c['baseline_version']['major']}.{c['baseline_version']['minor']}, hash={c['baseline_version']['sha256'][:8]})"
        else:
            line += " (new document, no baseline — use target_kind=document + expected_action=add)"
        if c.get("existing_targets"):
            targets = [
                f"{t['target_key']}(fields={t.get('allowed_fields', [])})"
                for t in c["existing_targets"]
            ]
            line += f" existing: {targets}"
        if c.get("add_anchors"):
            unique = list({(a['parent_node_id'], a['node_type']) for a in c['add_anchors']})
            line += f" can-add-under: {[f'{p}/{t}' for p,t in unique]}"
        doc_lines.append(line)

    return f"""你是一个质量工程师的文档影响分析助手。
请根据以下 8D 报告内容，分析哪些受控文档（控制计划 CP、FMEA）需要更新。

8D 信息：
- 产品线: {capa.product_line_code}
- 根因: {capa.d4_root_cause or '（未填写）'}
- 永久措施: {capa.d5_correction or '（未填写）'}
- 预防复发: {capa.d7_prevention or '（未填写）'}
- 严重度: {capa.severity}
- 关联 FMEA: {capa.fmea_ref_id or '（无）'}

可影响的文档（仅从以下清单选择）：
{chr(10).join(doc_lines)}

请以 JSON 格式输出 affected_docs 列表，每项含：
- doc_id: 从上面清单中选择的文档 ID
- key_points: 关键更新点列表，每项含：
  - target_kind: "fmea_node" | "cp_item" | "document"
  - expected_action: "add" | "modify" | "delete"
  - field: 字段名（必须来自 existing 的 allowed fields；add 时也须声明目标字段）
  - 对于 modify/delete: target_key（必须等于 existing 中的完整 target_key；CP 为 item_id；FMEA 为 node_id）
  - 对于 add: add_anchor = {{parent_node_id, node_type, business_key}}
- update_suggestion: 更新建议文本

约束：
- key_points 每项不可为空
- doc_id 仅从上方清单选择
- field 必须在该 target 的 allowed fields 内
- 新增项必须用 add_anchor 表达，不得编造不存在的 node_id
- document target_kind 仅用于 baseline 为空的新文档（FMEA 或 CP），expected_action 必须为 add"""


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "affected_docs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "key_points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target_kind": {"type": "string"},
                                "expected_action": {"type": "string"},
                                "field": {"type": "string"},
                                "target_key": {"type": "string"},
                                "add_anchor": {
                                    "type": "object",
                                    "properties": {
                                        "parent_node_id": {"type": "string"},
                                        "node_type": {"type": "string"},
                                        "business_key": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                    "update_suggestion": {"type": "string"},
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Validation: allowlist + vacuous pass + discriminant union
# ---------------------------------------------------------------------------

def _validate_and_backfill(phase2: dict, candidates: list[dict]) -> list[dict] | str:
    """Validate LLM output; backfill doc_id/name/baseline from allowlist. Return affected_docs or error str.

    Empty affected_docs is a VALID done state (spec C4): the LLM concluded no
    documents need updating; the engineer must then call confirm_no_affected.
    The vacuous-pass guard (per-doc key_points >= 1) only applies to non-empty lists.
    """
    raw_docs = phase2.get("affected_docs")
    if not isinstance(raw_docs, list):
        return "LLM 输出缺 affected_docs"
    if not raw_docs:
        return []
    cand_by_id = {str(c["doc_id"]): c for c in candidates}
    seen_doc_ids: set[str] = set()
    out = []
    for d in raw_docs:
        if not isinstance(d, dict):
            return "affected_docs 项必须为对象"
        doc_id = str(d.get("doc_id", ""))
        if doc_id not in cand_by_id:
            return f"LLM 输出非法 doc_id: {doc_id}"
        if doc_id in seen_doc_ids:
            return f"重复 affected document: {doc_id}"
        seen_doc_ids.add(doc_id)
        cand = cand_by_id[doc_id]
        kps = d.get("key_points", [])
        if not isinstance(kps, list):
            return "key_points 必须为数组"
        if not kps:
            return "doc key_points 为空（vacuous pass）"
        suggestion = d.get("update_suggestion")
        if not suggestion or not str(suggestion).strip():
            return "update_suggestion 为空"
        seen_kps: set[str] = set()
        for kp in kps:
            if not isinstance(kp, dict):
                return "key_point 必须为对象"
            err = _validate_key_point(kp, cand)
            if err:
                return err
            # Dedup key: action+kind+target_key or action+kind+add_anchor triple
            if kp.get("expected_action") == "add" and kp.get("add_anchor"):
                a = kp["add_anchor"] if isinstance(kp.get("add_anchor"), dict) else {}
                ksig = f"add|{kp.get('target_kind')}|{a.get('parent_node_id')}|{a.get('node_type')}|{str(a.get('business_key','')).strip().lower()}|{kp.get('field','')}"
            elif kp.get("target_kind") == "document":
                ksig = f"document|add"
            else:
                ksig = f"{kp.get('expected_action')}|{kp.get('target_kind')}|{kp.get('target_key')}|{kp.get('field','')}"
            if ksig in seen_kps:
                return f"重复 key_point: {ksig}"
            seen_kps.add(ksig)
        out.append({
            "doc_type": cand["doc_type"], "doc_id": cand["doc_id"], "doc_name": cand["doc_name"],
            "baseline_version_id": str(cand["baseline_version_id"]) if cand.get("baseline_version_id") else None,
            "baseline_version": cand.get("baseline_version"),
            "key_points": kps, "update_suggestion": suggestion,
        })
    return out


# Fields that may be required on add for each doc kind (field must be non-empty on new item/node)
_CP_ADD_FIELDS = {
    "control_method", "reaction_plan", "special_class", "sample_size", "sample_frequency",
    "product_characteristic", "process_characteristic",
}
_FMEA_ADD_FIELDS = {"prevention_control", "detection_control", "name"}


def _validate_key_point(kp: dict, cand: dict) -> str | None:
    action = kp.get("expected_action")
    if action not in ("add", "modify", "delete"):
        return f"非法 expected_action: {action}"
    kind = kp.get("target_kind")
    if kind not in ("fmea_node", "cp_item", "document"):
        return f"非法 target_kind: {kind}"
    # Presence (not truthiness) for discriminant mutual exclusion
    has_target_key = "target_key" in kp
    has_add_anchor = "add_anchor" in kp
    # document: baseline=NULL + add only; allowed for FMEA and CP (new docs after CAPA)
    if kind == "document":
        if cand["doc_type"] not in ("fmea", "control_plan"):
            return "document target_kind 仅用于 fmea/control_plan"
        if action != "add":
            return "document 仅允许 expected_action=add"
        if cand.get("baseline_version") is not None:
            return "document add 仅允许 baseline=NULL"
        if has_target_key or has_add_anchor:
            return "document add 不得带 target_key/add_anchor"
        return None
    if not (
        (kind == "cp_item" and cand["doc_type"] == "control_plan")
        or (kind == "fmea_node" and cand["doc_type"] == "fmea")
    ):
        return "doc_type/target_kind 错配"
    if has_target_key and has_add_anchor:
        return "target_key 与 add_anchor 互斥"
    if action in ("modify", "delete"):
        if not has_target_key or not str(kp.get("target_key") or "").strip():
            return f"{action} 须 target_key"
        existing = {t["target_key"]: t for t in cand.get("existing_targets", [])}
        if kp["target_key"] not in existing:
            return f"target_key 不在 allowlist: {kp['target_key']}"
        field = kp.get("field")
        if not field or not str(field).strip():
            return f"{action} 须 field"
        allowed_fields = set(existing[kp["target_key"]].get("allowed_fields", []))
        if str(field) not in allowed_fields:
            return f"field '{field}' 不在允许字段: {sorted(allowed_fields)}"
    if action == "add":
        if not has_add_anchor or not isinstance(kp.get("add_anchor"), dict) or not kp["add_anchor"]:
            return "add 须 add_anchor"
        if has_target_key:
            return "add 不得带 target_key"
        a = kp["add_anchor"]
        if not a.get("parent_node_id") or not a.get("node_type") or not str(a.get("business_key", "")).strip():
            return "add_anchor 三字段须非空"
        if a["node_type"] not in _ALLOWED_NODE_TYPES:
            return f"非法 node_type: {a['node_type']}"
        allowed_parents = {(x["parent_node_id"], x["node_type"]) for x in cand.get("add_anchors", [])}
        if (a["parent_node_id"], a["node_type"]) not in allowed_parents:
            return "add_anchor 不在 allowlist"
        field = kp.get("field")
        if not field or not str(field).strip():
            return "add 须 field"
        allowed = _CP_ADD_FIELDS if kind == "cp_item" else _FMEA_ADD_FIELDS
        if str(field) not in allowed:
            return f"add field '{field}' 不在允许字段: {sorted(allowed)}"
    return None

# ---------------------------------------------------------------------------
# run_audit: synchronous DB-query audit (no LLM) — Task 3
# ---------------------------------------------------------------------------

from app.services.diff_engine import diff_fmea_graphs, diff_cp_headers


async def run_audit(db: AsyncSession, capa: CAPAEightD, user_id: uuid.UUID) -> dict:
    """Audit each affected doc's version bump + key-point coverage. Insert audit + decision rows."""
    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.is_current == True
        )
    )
    if analysis is None or analysis.status != "done":
        raise ValueError("未生成有效影响分析")
    # C9 precheck
    candidates = await _build_allowlist(db, capa)
    cur_hash = _compute_input_hash(capa, candidates)
    if cur_hash != analysis.analysis_input_hash:
        raise ValueError("分析输入已变更，请重新生成影响分析")
    if not analysis.affected_docs:
        raise ValueError("空影响清单须人工确认，不可运行自动审核")
    audit_run_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    audits = []
    all_passed = True
    version_snapshot = []
    for doc in analysis.affected_docs:
        audit_row = await _audit_one_doc(db, capa, doc, audit_run_id, user_id, now)
        audits.append(audit_row)
        if audit_row["status"] != "passed":
            all_passed = False
        # Store version snapshot for ALL docs (even when blocked) so
        # C8 can re-verify non-waived docs after waiver.
        version_snapshot.append({
            "doc_type": doc["doc_type"], "doc_id": doc["doc_id"],
            "version_after_id": audit_row["version_after"]["version_id"] if audit_row["version_after"] else None,
            "sha256": audit_row["version_after"]["sha256"] if audit_row["version_after"] else None,
        })
    # Insert audit rows
    for a in audits:
        db.add(CapaDocgAudit(
            analysis_id=analysis.analysis_id, audit_run_id=audit_run_id, factory_id=capa.factory_id,
            doc_type=a["doc_type"], doc_id=a["doc_id"], doc_name=a["doc_name"], status=a["status"],
            version_before=a["version_before"], version_after=a["version_after"], version_bump=a["version_bump"],
            coverage=a["coverage"], covered_count=a["covered_count"], total_count=a["total_count"],
            audited_by=user_id, audited_at=now,
        ))
    # Insert decision (revision locked). audit_run_id is set for BOTH passed and
    # blocked (review P1#8: blocked needs the batch link for traceability).
    decision = "passed" if all_passed else "blocked"
    await _insert_decision(db, analysis.analysis_id, capa.factory_id, decision, user_id, now,
                          audit_run_id, version_snapshot)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id,
        action="DOC_UPDATE_AUDITED",
        changed_fields={"per_doc_status": [{"doc_type": a["doc_type"], "status": a["status"]} for a in audits], "audit_run_id": str(audit_run_id), "decision": decision},
        operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
    ))
    if all_passed:
        # review P1#8: emit the gate-passed event so the audit chain has an
        # explicit terminal marker (DOC_UPDATE_AUDITED = batch record,
        # DOC_GATE_PASSED = gate decision).
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id, action="DOC_GATE_PASSED",
            changed_fields={
                "audit_run_id": str(audit_run_id),
                "doc_count": len(audits),
                "no_affected_confirmed": False,
            },
            operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
        ))
    else:
        pending = [a["doc_id"] for a in audits if a["status"] == "pending_update"]
        incomplete = [a["doc_id"] for a in audits if a["status"] == "incomplete"]
        db.add(AuditLog(
            table_name="capa_eightd", record_id=capa.report_id, action="DOC_GATE_BLOCKED",
            changed_fields={
                "audit_run_id": str(audit_run_id),
                "per_doc_status": [{"doc_type": a["doc_type"], "status": a["status"]} for a in audits],
                "pending_docs": [str(x) for x in pending],
                "incomplete_docs": [str(x) for x in incomplete],
            },
            operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
        ))
    await db.commit()
    return {"decision": decision, "audits": audits, "audit_run_id": str(audit_run_id)}


async def _insert_decision(db, analysis_id, factory_id, decision, user_id, now, audit_run_id, version_snapshot,
                          defer_reason=None, defer_owner=None, defer_deadline=None, no_affected_confirmed=False,
                          waiver_reason=None, waiver_items=None):
    """Lock analysis row, read max revision, insert revision+1 (UQ (analysis_id, revision) guards concurrency).
    defer fields + no_affected_confirmed + waiver_reason/items passed at insert time
    (CHECK requires defer fields for deferred; waiver only on passed with non-empty items)."""
    await db.execute(text("SELECT 1 FROM capa_docg_analysis WHERE analysis_id=:aid FOR UPDATE"), {"aid": analysis_id})
    max_rev = await db.scalar(
        select(CapaDocgDecision.revision).where(CapaDocgDecision.analysis_id == analysis_id)
        .order_by(CapaDocgDecision.revision.desc()).limit(1)
    )
    db.add(CapaDocgDecision(
        analysis_id=analysis_id, audit_run_id=audit_run_id,
        revision=(max_rev if max_rev is not None else -1) + 1,
        factory_id=factory_id, decision=decision, version_snapshot=version_snapshot,
        defer_reason=defer_reason, defer_owner=defer_owner, defer_deadline=defer_deadline,
        no_affected_confirmed=no_affected_confirmed,
        waiver_reason=waiver_reason, waiver_items=waiver_items,
        decided_by=user_id, decided_at=now,
    ))


async def _audit_one_doc(db, capa, doc, audit_run_id, user_id, now):
    doc_type = doc["doc_type"]
    doc_id = uuid.UUID(str(doc["doc_id"]))
    baseline_meta = doc.get("baseline_version")
    baseline_version_id = doc.get("baseline_version_id")
    # Re-fetch baseline version snapshot from DB (affected_docs only stores meta {major,minor,sha256})
    baseline_snapshot = None
    if baseline_version_id:
        from app.models.control_plan_version import ControlPlanVersion
        from app.models.fmea_version import FMEAVersion
        bvid = uuid.UUID(str(baseline_version_id))
        if doc_type == "control_plan":
            bver = await db.get(ControlPlanVersion, bvid)
            # Store full CP snapshot {header, items} — _compute_diff reads both
            # (review P1#4: was header_snapshot only → baseline items always empty)
            if bver is not None:
                baseline_snapshot = {
                    "header": bver.header_snapshot or {},
                    "items": (bver.items_snapshot.get("items", []) if isinstance(bver.items_snapshot, dict) else (bver.items_snapshot or [])),
                }
        else:
            bver = await db.get(FMEAVersion, bvid)
            baseline_snapshot = bver.snapshot if bver else None
    # Latest version (factory filter applied inside get_latest_* by doc_id; doc_id trusted via allowlist)
    if doc_type == "control_plan":
        latest = await get_latest_cp_version(db, doc_id)
    else:
        latest = await get_latest_fmea_version(db, doc_id)
    version_after = None
    version_bump = False
    if latest and latest.created_at > capa.created_at:
        version_after = {"version_id": str(latest.version_id), "major": latest.major_no, "minor": latest.minor_no, "sha256": latest.sha256_hash, "updated_at": latest.created_at.isoformat()}
        if baseline_meta is None or baseline_meta.get("sha256") != latest.sha256_hash:
            version_bump = True
    version_before = None
    if baseline_meta:
        version_before = {"version_id": baseline_version_id, "major": baseline_meta["major"], "minor": baseline_meta["minor"], "sha256": baseline_meta["sha256"]}
    coverage = []
    covered = 0
    total = len(doc["key_points"])
    if version_bump and version_after:
        diff = _compute_diff(doc_type, baseline_snapshot, latest)
        for kp in doc["key_points"]:
            hit = _match_key_point(kp, diff, latest, doc_type)
            coverage.append({"key_point": kp, "covered": hit, "evidence": ""})
            if hit:
                covered += 1
    else:
        for kp in doc["key_points"]:
            coverage.append({"key_point": kp, "covered": False, "evidence": ""})
    status = "passed" if (version_bump and covered == total) else ("incomplete" if version_bump else "pending_update")
    return {"doc_type": doc_type, "doc_id": doc_id, "doc_name": doc["doc_name"], "status": status,
            "version_before": version_before, "version_after": version_after, "version_bump": version_bump,
            "coverage": coverage, "covered_count": covered, "total_count": total}


def _diff_cp_items_for_gate(v1_items: list[dict], v2_items: list[dict]) -> dict:
    """CP diff for doc-gate: item_id is the sole identity (contract v2).

    Pair strictly by item_id. Content-shape fingerprint remap is intentionally
    NOT used: delete-all + recreate with the same source/product/process would
    look identical to a historical whole-table UUID rebuild, and product/process
    themselves are mutable fields so fingerprints miss real rebuilds that also
    edited those fields. Historical identity breaks require re-analysis after
    CP re-save (item_id preserved) or DOC_GATE_CONTRACT_VERSION invalidation.
    """
    v1_by_id = {_cp_item_id(i): i for i in v1_items if _cp_item_id(i)}
    v2_by_id = {_cp_item_id(i): i for i in v2_items if _cp_item_id(i)}
    shared_ids = set(v1_by_id) & set(v2_by_id)
    modified = []
    for iid in sorted(shared_ids):
        old, new = v1_by_id[iid], v2_by_id[iid]
        changes = []
        for key in sorted((set(old) | set(new)) - {"item_id"}):
            if old.get(key) != new.get(key):
                changes.append({"field": key, "old": old.get(key), "new": new.get(key)})
        if changes:
            modified.append({
                "item_id": iid,
                "source_fmea_node_id": new.get("source_fmea_node_id"),
                "changes": changes,
                "new_item": new,
            })
    deleted = [v1_by_id[i] for i in sorted(set(v1_by_id) - shared_ids)]
    added = [v2_by_id[i] for i in sorted(set(v2_by_id) - shared_ids)]
    return {"added_items": added, "deleted_items": deleted, "modified_items": modified}


def _compute_diff(doc_type, baseline_snapshot, latest):
    if doc_type == "control_plan":
        v1_items = (baseline_snapshot or {}).get("items", []) if isinstance(baseline_snapshot, dict) else []
        v2_items = (latest.items_snapshot.get("items", []) if isinstance(latest.items_snapshot, dict) else (latest.items_snapshot or []))
        v1_header = (baseline_snapshot or {}).get("header", {}) if isinstance(baseline_snapshot, dict) else {}
        v2_header = latest.header_snapshot or {}
        return {"items": _diff_cp_items_for_gate(v1_items, v2_items), "headers": diff_cp_headers(v1_header, v2_header)}
    else:
        v1 = baseline_snapshot if isinstance(baseline_snapshot, dict) else {"nodes": [], "edges": []}
        v2 = latest.snapshot or {"nodes": [], "edges": []}
        return diff_fmea_graphs(v1, v2)


def _build_parent_map(snapshot: dict) -> dict:
    """target_id -> [source_ids] from snapshot edges."""
    parent_map = {}
    for e in (snapshot or {}).get("edges", []):
        src = e.get("source"); tgt = e.get("target")
        if src and tgt:
            parent_map.setdefault(tgt, []).append(src)
    return parent_map


def _field_nonempty(obj: dict, field: str) -> bool:
    val = obj.get(field)
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    return True


def _match_key_point(kp, diff, latest, doc_type):
    """Return True if the key_point is covered by the version diff.

    CP: target_key = item_id (baseline). modify/delete match strictly by item_id.
    add uses parent+business_key+non-empty field.
    """
    action = kp["expected_action"]
    kind = kp.get("target_kind")
    if kind == "document":
        return action == "add"
    if doc_type == "control_plan":
        items_diff = diff["items"]
        if action == "modify":
            field = kp.get("field")
            return any(
                str(i.get("item_id", "")) == str(kp["target_key"])
                and any(c.get("field") == field for c in i.get("changes", []))
                for i in items_diff["modified_items"]
            )
        if action == "delete":
            return any(str(i.get("item_id", "")) == str(kp["target_key"]) for i in items_diff["deleted_items"])
        if action == "add":
            a = kp["add_anchor"]
            field = kp.get("field")
            bk = str(a["business_key"]).strip().lower()
            return any(
                str(i.get("source_fmea_node_id", "")).strip().lower() == str(a["parent_node_id"]).strip().lower()
                and (
                    str(i.get("product_characteristic", "")).strip().lower() == bk
                    or str(i.get("process_characteristic", "")).strip().lower() == bk
                )
                and _field_nonempty(i, field)
                for i in items_diff["added_items"]
            )
    else:  # fmea
        g_diff = diff
        if action == "modify":
            field = kp.get("field")
            return any(
                n.get("node_id") == kp["target_key"] and any(c.get("field") == field for c in n.get("changes", []))
                for n in g_diff["modified_nodes"]
            )
        if action == "delete":
            return any(n.get("id") == kp["target_key"] for n in g_diff["deleted_nodes"])
        if action == "add":
            a = kp["add_anchor"]
            field = kp.get("field")
            bk = str(a["business_key"]).strip().lower()
            parent_map = _build_parent_map(latest.snapshot)
            return any(
                a["parent_node_id"] in parent_map.get(n["id"], [])
                and n.get("type") == a["node_type"]
                and str(n.get("name", "")).strip().lower() == bk
                and _field_nonempty(n, field)
                for n in g_diff["added_nodes"]
            )
    return False


# ---------------------------------------------------------------------------
# record_defer + confirm_no_affected (Task 4)
# ---------------------------------------------------------------------------

async def record_defer(db: AsyncSession, capa: CAPAEightD, reason: str, owner_id: uuid.UUID, deadline, user_id: uuid.UUID) -> dict:
    """Record a deferred decision (still blocks the gate — C5). Owner validated against capa factory.

    Factory authorization: accept if primary factory matches OR UserFactory
    association includes capa.factory_id. bypass_row_level_security only bypasses
    product-line filtering, NOT factory scope (factory_scope.py docstring) — do
    not treat it as group-admin cross-factory access.
    """
    if not reason or not str(reason).strip():
        raise ValueError("defer reason 必填")
    from app.models.user import User
    from app.core.factory_scope import get_user_factory_ids
    owner = await db.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise ValueError("defer_owner 不存在或未激活")
    if owner.factory_id != capa.factory_id:
        user_fids = await get_user_factory_ids(owner, db)
        if capa.factory_id not in user_fids:
            raise ValueError("defer_owner 无当前工厂授权")
    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.is_current == True
        )
    )
    if analysis is None:
        raise ValueError("未生成影响分析")
    # C9 precheck
    candidates = await _build_allowlist(db, capa)
    if _compute_input_hash(capa, candidates) != analysis.analysis_input_hash:
        raise ValueError("分析输入已变更，请重新生成影响分析")
    from datetime import date as date_cls
    dl = deadline if isinstance(deadline, date_cls) else date_cls.fromisoformat(str(deadline))
    now = datetime.now(timezone.utc)
    await _insert_decision(db, analysis.analysis_id, capa.factory_id, "deferred", user_id, now, None, [],
                          defer_reason=reason, defer_owner=owner_id, defer_deadline=dl)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id, action="DOC_GATE_DEFERRED",
        changed_fields={"reason": reason, "owner": str(owner_id), "deadline": str(dl)},
        operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
    ))
    await db.commit()
    return {"decision": "deferred"}


async def confirm_no_affected(db: AsyncSession, capa: CAPAEightD, user_id: uuid.UUID) -> dict:
    """Engineer confirms an empty affected_docs list is correct -> decision=passed (no_affected_confirmed)."""
    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.is_current == True
        )
    )
    if analysis is None or analysis.status != "done":
        raise ValueError("未生成有效影响分析")
    candidates = await _build_allowlist(db, capa)
    if _compute_input_hash(capa, candidates) != analysis.analysis_input_hash:
        raise ValueError("分析输入已变更，请重新生成影响分析")
    if analysis.affected_docs:
        raise ValueError("仅空清单可确认")
    now = datetime.now(timezone.utc)
    await _insert_decision(db, analysis.analysis_id, capa.factory_id, "passed", user_id, now, None, [],
                          no_affected_confirmed=True)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id, action="DOC_GATE_PASSED",
        changed_fields={"reason": "空清单人工确认", "no_affected_confirmed": True, "doc_count": 0},
        operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
    ))
    await db.commit()
    return {"decision": "passed", "no_affected_confirmed": True}


async def record_gate_waiver(
    db: AsyncSession,
    capa: CAPAEightD,
    reason: str,
    items: list[dict],
    user_id: uuid.UUID,
) -> dict:
    """Waive exact blocked_modify CP keypoints after a blocked audit.

    Fail-closed rules:
    - Requires current analysis + latest decision=blocked (from run_audit).
    - Each item must be control_plan / cp_item / modify, uncovered in the blocked
      audit, and still absent from the live latest CP.
    - Residual completeness: EVERY uncovered keypoint in the audit batch must be
      either covered already or listed in items. Non-waivable residuals
      (FMEA / pending_update no-bump / incomplete add-delete / other fields)
      reject the whole waiver — a partial local waiver cannot pass the batch.
    - C8 version_snapshot keeps ALL docs (including waived ones), bound to the
      live version at waiver time. Gate re-checks version_id+sha256 AND that
      each waived target_key is still absent.
    - TOCTOU: analysis row is locked before re-reading the latest decision.

    Caller must require APPROVE permission on the capa module (enforced in API).
    """
    if not reason or not str(reason).strip():
        raise ValueError("waiver reason 必填")
    if not items:
        raise ValueError("waiver items 必填（至少一个 blocked_modify keypoint）")

    # Phase A: locate current analysis (no lock yet — may 404 early)
    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(
            CapaDocgAnalysis.capa_id == capa.report_id, CapaDocgAnalysis.is_current == True  # noqa: E712
        )
    )
    if analysis is None or analysis.status != "done":
        raise ValueError("未生成影响分析")

    # Phase B: lock analysis, then re-read latest decision under the lock (TOCTOU)
    await db.execute(
        text("SELECT 1 FROM capa_docg_analysis WHERE analysis_id=:aid FOR UPDATE"),
        {"aid": analysis.analysis_id},
    )
    latest_decision = await db.scalar(
        select(CapaDocgDecision).where(CapaDocgDecision.analysis_id == analysis.analysis_id)
        .order_by(CapaDocgDecision.revision.desc()).limit(1)
    )
    if latest_decision is None:
        raise ValueError("请先运行文档审核")
    if latest_decision.decision != "blocked":
        raise ValueError(f"当前决策状态为 {latest_decision.decision}，只能豁免已阻塞的审核")
    if latest_decision.audit_run_id is None:
        raise ValueError("blocked 决策缺少 audit_run_id，请重新运行文档审核")

    from app.services.capa_doc_gate_waiver import prepare_structured_waiver

    validated, c8_snapshot = await prepare_structured_waiver(
        db, analysis, latest_decision.audit_run_id, items
    )

    now = datetime.now(timezone.utc)
    await _insert_decision(
        db, analysis.analysis_id, capa.factory_id, "passed", user_id, now,
        latest_decision.audit_run_id, c8_snapshot,
        no_affected_confirmed=False,
        waiver_reason=reason,
        waiver_items=validated,
    )
    db.add(AuditLog(
        table_name="capa_eightd", record_id=capa.report_id, action="DOC_GATE_WAIVER",
        changed_fields={
            "reason": reason,
            "decision_from": "blocked",
            "decision_to": "passed",
            "audit_run_id": str(latest_decision.audit_run_id),
            "waiver_items": validated,
        },
        operated_by=user_id, factory_id=capa.factory_id, operated_at=now,
    ))
    await db.commit()
    return {
        "decision": "passed",
        "waiver_reason": reason,
        "waiver_items": validated,
        "audit_run_id": str(latest_decision.audit_run_id),
    }
