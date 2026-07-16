"""Fail-closed validation for structured D8 document-gate waivers."""
from __future__ import annotations

from collections import Counter
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit
from app.services.version_service import (
    get_latest_cp_version,
    get_latest_fmea_version,
    lock_version_parent,
)


def _identity(doc_type, doc_id) -> tuple[str, str]:
    kind = str(doc_type or "").strip()
    try:
        canonical_id = str(uuid.UUID(str(doc_id)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"非法 doc_id: {doc_id}")
    if kind not in {"control_plan", "fmea"}:
        raise ValueError(f"不支持的审核文档类型: {kind}")
    return kind, canonical_id


def _item_ids(items_snapshot) -> set[str]:
    if isinstance(items_snapshot, dict):
        items = items_snapshot.get("items", [])
    elif isinstance(items_snapshot, list):
        items = items_snapshot
    else:
        items = []
    return {
        str(item.get("item_id"))
        for item in items
        if isinstance(item, dict) and item.get("item_id")
    }


async def prepare_structured_waiver(
    db: AsyncSession,
    analysis: CapaDocgAnalysis,
    audit_run_id: uuid.UUID,
    raw_items: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Validate an exact blocked audit batch and return waiver items + C8 snapshot."""
    audits = (await db.execute(
        select(CapaDocgAudit).where(
            CapaDocgAudit.analysis_id == analysis.analysis_id,
            CapaDocgAudit.audit_run_id == audit_run_id,
        )
    )).scalars().all()
    if not audits:
        raise ValueError("找不到对应审核批次，请重新运行文档审核")

    analysis_docs = analysis.affected_docs
    if not isinstance(analysis_docs, list) or not analysis_docs:
        raise ValueError("影响分析文档清单异常，请重新生成影响分析")
    analysis_identities: list[tuple[str, str]] = []
    analysis_by_identity: dict[tuple[str, str], dict] = {}
    for doc in analysis_docs:
        if not isinstance(doc, dict):
            raise ValueError("影响分析文档清单异常，请重新生成影响分析")
        identity = _identity(doc.get("doc_type"), doc.get("doc_id"))
        analysis_identities.append(identity)
        analysis_by_identity[identity] = doc
    audit_identities = [_identity(a.doc_type, a.doc_id) for a in audits]
    if (
        len(set(analysis_identities)) != len(analysis_identities)
        or len(set(audit_identities)) != len(audit_identities)
        or set(analysis_identities) != set(audit_identities)
    ):
        raise ValueError("审核批次文档与影响分析不一致，请重新运行审核")

    uncovered: dict[tuple[str, str, str, str], dict] = {}
    non_waivable: list[tuple[str, str]] = []
    for audit in audits:
        identity = _identity(audit.doc_type, audit.doc_id)
        coverage = audit.coverage
        if not isinstance(coverage, list):
            raise ValueError("审核覆盖明细异常，请重新运行审核")
        analysis_keypoints = analysis_by_identity[identity].get("key_points")
        if not isinstance(analysis_keypoints, list):
            raise ValueError("影响分析 key_points 异常，请重新生成影响分析")
        if (
            len(coverage) != audit.total_count
            or audit.total_count != len(analysis_keypoints)
            or audit.covered_count
            != sum(1 for cov in coverage if isinstance(cov, dict) and cov.get("covered") is True)
        ):
            raise ValueError("审核覆盖明细不完整，请重新运行审核")
        coverage_keypoints = [cov.get("key_point") for cov in coverage if isinstance(cov, dict)]
        if (
            len(coverage_keypoints) != len(coverage)
            or any(not isinstance(kp, dict) for kp in coverage_keypoints)
            or Counter(json.dumps(kp, sort_keys=True) for kp in coverage_keypoints)
            != Counter(json.dumps(kp, sort_keys=True) for kp in analysis_keypoints)
        ):
            raise ValueError("审核覆盖 key_points 与影响分析不一致，请重新运行审核")
        for cov in coverage:
            if not isinstance(cov, dict) or not isinstance(cov.get("covered"), bool):
                raise ValueError("审核覆盖明细异常，请重新运行审核")
            kp = cov.get("key_point")
            if not isinstance(kp, dict):
                raise ValueError("审核覆盖明细异常，请重新运行审核")
            if cov["covered"]:
                continue
            target_key = str(kp.get("target_key") or "").strip()
            field = str(kp.get("field") or "").strip()
            if (
                identity[0] != "control_plan"
                or kp.get("expected_action") != "modify"
                or kp.get("target_kind") != "cp_item"
                or not target_key
                or not field
            ):
                non_waivable.append(identity)
                continue
            key = (identity[0], identity[1], target_key, field)
            if key in uncovered:
                raise ValueError("审核覆盖明细含重复 blocked_modify，请重新运行审核")
            uncovered[key] = {
                "doc_type": identity[0],
                "doc_id": identity[1],
                "target_key": target_key,
                "field": field,
            }
    if not uncovered:
        raise ValueError(
            "本批次无 blocked_modify（CP item_id 断链）可豁免项；"
            "pending_update/incomplete/add/delete/FMEA 须先修正文档后重审"
        )
    if non_waivable:
        doc_type, doc_id = non_waivable[0]
        raise ValueError(
            "仍有不可豁免的阻塞项（须先修正文档后重审）: "
            f"doc_type={doc_type} doc_id={doc_id} (共 {len(non_waivable)} 项)"
        )

    requested: dict[tuple[str, str, str, str], dict] = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("waiver item 格式非法")
        doc_type = str(raw.get("doc_type") or "").strip()
        doc_id_s = str(raw.get("doc_id") or "").strip()
        target_key = str(raw.get("target_key") or "").strip()
        field = str(raw.get("field") or "").strip()
        if doc_type != "control_plan":
            raise ValueError("仅允许豁免 control_plan 的 blocked_modify")
        if not doc_id_s or not target_key or not field:
            raise ValueError("waiver item 缺 doc_id/target_key/field")
        identity = _identity(doc_type, doc_id_s)
        key = (identity[0], identity[1], target_key, field)
        if key in requested:
            raise ValueError(f"重复 waiver item: {target_key}/{field}")
        requested[key] = {
            "doc_type": identity[0],
            "doc_id": identity[1],
            "target_key": target_key,
            "field": field,
        }

    extra = set(requested) - set(uncovered)
    if extra:
        kind, doc_id, target_key, field = next(iter(extra))
        raise ValueError(
            "keypoint 不在 blocked audit 的未覆盖 modify 集合中: "
            f"doc={doc_id} target_key={target_key} field={field}"
        )
    missing = set(uncovered) - set(requested)
    if missing:
        _, doc_id, target_key, field = next(iter(missing))
        raise ValueError(
            "局部豁免被拒绝：同批次仍有未覆盖的 blocked_modify 未列入 items: "
            f"doc_id={doc_id} target_key={target_key} field={field} "
            f"(共 {len(missing)} 项)"
        )

    # Shared serialization with production version writers. Acquire every parent
    # in deterministic order before any live latest read, then hold through the
    # caller's decision insert + commit.
    for doc_type, doc_id in sorted(set(audit_identities)):
        await lock_version_parent(db, doc_type, uuid.UUID(doc_id))

    live_by_identity = {}
    c8_snapshot: list[dict] = []
    for audit in audits:
        doc_type, doc_id = _identity(audit.doc_type, audit.doc_id)
        live = (
            await get_latest_cp_version(db, uuid.UUID(doc_id))
            if doc_type == "control_plan"
            else await get_latest_fmea_version(db, uuid.UUID(doc_id))
        )
        version_after = audit.version_after
        if (
            live is None
            or not isinstance(version_after, dict)
            or str(live.version_id) != str(version_after.get("version_id") or "")
            or live.sha256_hash != version_after.get("sha256")
        ):
            raise ValueError("审核后文档已变更，请重新运行审核")
        live_by_identity[(doc_type, doc_id)] = live
        c8_snapshot.append({
            "doc_type": doc_type,
            "doc_id": doc_id,
            "version_after_id": str(version_after["version_id"]),
            "sha256": version_after["sha256"],
        })

    enriched: list[dict] = []
    for key in requested:
        doc_type, doc_id, target_key, field = key
        live = live_by_identity[(doc_type, doc_id)]
        if target_key in _item_ids(live.items_snapshot):
            raise ValueError(
                f"target_key={target_key} 已存在于 latest 版本，不是 blocked_modify 断链；"
                "请重新审核或修正 CP"
            )
        enriched.append({
            **requested[key],
            "latest_version_id": str(live.version_id),
            "latest_sha256": live.sha256_hash,
            "audit_run_id": str(audit_run_id),
        })
    return enriched, c8_snapshot
