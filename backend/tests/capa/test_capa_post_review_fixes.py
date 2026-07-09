"""Post-review fixes for US-E2E-01.3 state-machine slice.

P1 (concurrency): advance_capa must lock the CAPA row FOR UPDATE and re-read status,
  else two concurrent approve requests from D8_APPROVAL_PENDING both transition →
  duplicate TRANSITION/D8_APPROVED audit + MES events. Simulated by a raw UPDATE that
  changes the DB status without refreshing the in-memory capa object (stale state).

P2 (open-CAPA filter): rollback_fmea's cascade guard must use capa_open_clause (NOT IN
  D8_CLOSURE/ARCHIVED), so an ARCHIVED CAPA no longer blocks FMEA version rollback.
"""
import json
import uuid
import hashlib
import pytest
from sqlalchemy import select, text
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.schemas.capa import AdvanceRequest
from app.services.capa_service import advance_capa, get_capa
from app.services.version_service import rollback_fmea

pytestmark = pytest.mark.requires_db


def _pg_jsonb_hash(snapshot: dict) -> str:
    """Hash matching the DB trigger (migration 020): encode(digest(NEW.snapshot::text,'sha256'),'hex').
    Postgres JSONB::text uses sort_keys + default separators (', ' / ': '). Note: app-side
    compute_snapshot_hash uses compact separators — a pre-existing mismatch unrelated to P2."""
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()


async def _make_capa(db, factory_id, user_id, status):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-POST-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status=status, d5_correction="措施A",
        d6_verification="已验证", d7_prevention="预防",
    )
    db.add(capa); await db.flush()
    return capa


# ── P1: stale-state / concurrent advance rejection ──────────────────────────


@pytest.mark.asyncio
async def test_advance_rejects_stale_state_after_concurrent_transition(db, default_factory, admin_user):
    """P1: 另一事务已把 capa 从 D8_APPROVAL_PENDING 推进到 D8_CLOSURE 后，
    本请求的 in-memory capa.status 仍为 D8_APPROVAL_PENDING（陈旧）。
    advance_capa 必须 FOR UPDATE + 重新读取 → can_transition(D8_CLOSURE→D8_CLOSURE)=False → 拒绝，
    防重复 TRANSITION/D8_APPROVED 审计/MES 事件。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D8_APPROVAL_PENDING")
    # 模拟并发：raw UPDATE 改 DB 状态为 D8_CLOSURE，不刷新 ORM 对象 → capa.status 陈旧
    await db.execute(
        text("UPDATE capa_eightd SET status = 'D8_CLOSURE' WHERE report_id = :rid"),
        {"rid": capa.report_id},
    )
    # ORM 对象仍陈旧（raw UPDATE 不刷新 identity-mapped 属性）
    assert capa.status == "D8_APPROVAL_PENDING"

    # 修复后：advance_capa 锁行 + populate_existing 重读 → D8_CLOSURE → can_transition 拒绝
    with pytest.raises(ValueError, match="Cannot transition"):
        await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D8_CLOSURE"))


@pytest.mark.asyncio
async def test_advance_normal_path_still_works_with_lock(db, default_factory, admin_user):
    """P1 回归：锁不破坏正常推进路径。D7_COMPLETED→D8_GATE_PENDING 仍可推进。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D7_COMPLETED")
    await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D8_GATE_PENDING"))
    await db.refresh(capa)
    assert capa.status == "D8_GATE_PENDING"


# ── P2: ARCHIVED CAPA no longer blocks FMEA rollback ────────────────────────


async def _make_fmea_with_version(db, factory_id, user_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-ROLL-{uuid.uuid4().hex[:6]}",
        title="t", fmea_type="PFMEA", product_line_code="DC-DC-100",
        factory_id=factory_id, status="draft", created_by=user_id,
        graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea); await db.flush()
    snapshot = {"nodes": [], "edges": []}
    ver = FMEAVersion(
        version_id=uuid.uuid4(), fmea_id=fmea.fmea_id, factory_id=factory_id,
        major_no=1, minor_no=0, snapshot=snapshot,
        sha256_hash=_pg_jsonb_hash(snapshot), change_type="create", created_by=user_id,
    )
    db.add(ver); await db.flush()
    return fmea, ver


@pytest.mark.asyncio
async def test_archived_capa_does_not_block_fmea_rollback(db, default_factory, admin_user):
    """P2: ARCHIVED CAPA 不算活动引用 → cascade 不阻断。旧逻辑 status != 'D8_CLOSURE'
    把 ARCHIVED 误判为活动、抛「无法回退」。本测试只断言 cascade 不抛「无法回退」
    （rollback 后续版本创建可能因预先存在的 compute_snapshot_hash 与 trigger 不一致而
    另抛他错——那是独立 bug，不在 P2 范围）。"""
    fmea, ver = await _make_fmea_with_version(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "ARCHIVED")
    capa.fmea_ref_id = fmea.fmea_id; await db.flush()

    blocked_with_archived = False
    try:
        await rollback_fmea(db, fmea, target_major=1, target_minor=0,
                            reason="测试回退", user_id=admin_user.user_id)
    except Exception as e:
        # 容忍预先存在的版本创建 hash bug（compute_snapshot_hash 与 trigger 不一致，
        # 在 cascade 之后才触发）；只判定 cascade 是否误把 ARCHIVED 当活动阻断。
        blocked_with_archived = "无法回退" in str(e)
    assert not blocked_with_archived, "ARCHIVED CAPA 不应阻断 rollback（不应抛「无法回退」）"


@pytest.mark.asyncio
async def test_open_capa_still_blocks_fmea_rollback(db, default_factory, admin_user):
    """P2 回归：未关闭 CAPA（如 D8_APPROVAL_PENDING）仍阻断 rollback_fmea。"""
    fmea, ver = await _make_fmea_with_version(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D8_APPROVAL_PENDING")
    capa.fmea_ref_id = fmea.fmea_id; await db.flush()

    with pytest.raises(ValueError, match="无法回退"):
        await rollback_fmea(db, fmea, target_major=1, target_minor=0,
                            reason="测试回退", user_id=admin_user.user_id)