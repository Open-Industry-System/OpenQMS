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
from fastapi import HTTPException
from sqlalchemy import select, text, event
from contextlib import contextmanager
import re
from tests.conftest import _scope_for
from tests.capa.r6_support import r6_case  # noqa:F401
from app.core.permissions import Module, PermissionLevel
from app.models.capa import CAPAEightD
from app.models.audit import AuditLog
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.models.user import User
from app.schemas.capa import AdvanceRequest
from app.services.capa_service import advance_capa, get_capa
from app.services.capa_doc_gate_service import confirm_no_affected
from tests.capa.conftest import _make_done_analysis
from app.services.version_service import rollback_fmea
from app.api.capa import require_advance_permission

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


# ── P1 TOCTOU: two independent transactions ─────────────────────────────────


@contextmanager
def _capa_statements(engine):
    statements=[]
    def observe(conn,cursor,statement,parameters,context,executemany):statements.append(statement.lower().replace('"',''))
    event.listen(engine.sync_engine,'before_cursor_execute',observe)
    try:yield statements
    finally:event.remove(engine.sync_engine,'before_cursor_execute',observe)


def _from_capa(statement):
    return re.search(r'\bfrom\s+(?:[a-z0-9_]+\.)?capa_eightd\b',statement) is not None


@pytest.mark.asyncio
async def test_toctou_edit_user_cannot_approve_after_concurrent_advance(r6_case):
    """P1 TOCTOU（两个独立事务）：EDIT 用户在 capa=D8_GATE_PENDING 时请求 target=D8_CLOSURE
    （边无效 → 锁前按 EDIT 放行）；事务 B 先推进到 D8_APPROVAL_PENDING 并提交；事务 A 锁后
    刷新状态为 D8_APPROVAL_PENDING，(D8_APPROVAL_PENDING→D8_CLOSURE) 变合法 APPROVE 边。
    修复后 require_advance_permission 在 FOR UPDATE 锁+刷新后重做边权限校验 → EDIT 用户 403。
    （未修复时锁前 EDIT 决策成立、放行，advance_capa 越权完成审批——privilege bypass。）"""
    # Normal own-tenant provisioning and teardown retain immutable business
    # evidence during the test and drop only its owned schema afterwards.
    # Public fixture cleanup must never delete monotonic R6 counters.
    c=r6_case
    with _capa_statements(c.runtime.engine) as statements:
        # Setup (committed): EDIT user + capa D8_GATE_PENDING
        async with c.session() as s0:
            edit_user = await s0.get(User,c.actor().user_id)
            user_id = edit_user.user_id
            capa = CAPAEightD(
                report_id=uuid.uuid4(), document_no=f"8D-TOCTOU-{uuid.uuid4().hex[:6]}",
                title="t", product_line_code=c.line, factory_id=c.factory_id,
                created_by=edit_user.user_id, status="D8_GATE_PENDING", d5_correction="措施A",
                d6_verification="已验证", d7_prevention="预防",
            )
            s0.add(capa); await s0.commit()
            capa_id = capa.report_id

        # Session A (EDIT user's request): load capa stale (D8_GATE_PENDING) — pre-lock read
        async with c.session() as db_a:
            pid_a=await db_a.scalar(text("SELECT pg_backend_pid()"))
            capa_a = await get_capa(db_a, capa_id)
            assert capa_a.status == "D8_GATE_PENDING"  # stale baseline

            # Session B (concurrent approver): satisfy D8 doc gate, then advance → D8_APPROVAL_PENDING + commit
            async with c.session() as db_b:
                pid_b=await db_b.scalar(text("SELECT pg_backend_pid()"))
                assert pid_b!=pid_a
                capa_b = await get_capa(db_b, capa_id)
                # US-E2E-01.7 doc gate: need a passed decision before D8_GATE_PENDING→D8_APPROVAL_PENDING.
                await _make_done_analysis(db_b, capa_b, edit_user, [])
                await confirm_no_affected(db_b, capa_b, edit_user.user_id)
                await advance_capa(db_b, capa_b, edit_user.user_id,
                                   AdvanceRequest(target_state="D8_APPROVAL_PENDING"))
                await db_b.commit()
            # DB now D8_APPROVAL_PENDING; db_a's capa_a still stale (identity map)

            assert await db_a.scalar(select(CAPAEightD.status).where(CAPAEightD.report_id==capa_id))=='D8_APPROVAL_PENDING'
            assert capa_a.status=='D8_GATE_PENDING'
            factory_a = await db_a.get(Factory, c.factory_id)
            scope = _scope_for(edit_user, factory_a, accessible_factory_ids=None)
            # Fix: require_advance_permission locks+refreshes → fresh D8_APPROVAL_PENDING →
            # (D8_APPROVAL_PENDING→D8_CLOSURE) APPROVE edge → EDIT user 403.
            with pytest.raises(HTTPException) as exc:
                await require_advance_permission(
                    capa_id, AdvanceRequest(target_state="D8_CLOSURE"),
                    scope=scope, db=db_a,
                )
            assert exc.value.status_code == 403
            assert any(_from_capa(sql) and 'for update' in sql for sql in statements)
            assert any(_from_capa(sql) and 'capa_eightd.d4_root_cause' in sql for sql in statements)
            await db_a.rollback()
