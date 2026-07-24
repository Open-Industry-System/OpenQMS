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
from sqlalchemy import select, text, delete
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import _test_session_factory, _scope_for, DEFAULT_FACTORY_ID
from app.core.security import hash_password
from app.core.permissions import Module, PermissionLevel
from app.models.capa import CAPAEightD
from app.models.audit import AuditLog
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission
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


async def _ensure_edit_user(s: AsyncSession) -> tuple[User, uuid.UUID]:
    """Idempotent committed setup: factory + product line + EDIT-level role/user (capa=3)."""
    if await s.get(Factory, DEFAULT_FACTORY_ID) is None:
        s.add(Factory(id=DEFAULT_FACTORY_ID, code="TEST", name="Test Factory"))
        await s.flush()
    if (await s.execute(select(ProductLine).where(ProductLine.code == "DC-DC-100"))).scalar_one_or_none() is None:
        s.add(ProductLine(code="DC-DC-100", name="DC-DC Convert 100W", factory_id=DEFAULT_FACTORY_ID))
        await s.flush()
    role = (await s.execute(select(RoleDefinition).where(RoleDefinition.role_key == "test_toctou_edit"))).scalar_one_or_none()
    if role is None:
        role = RoleDefinition(role_key="test_toctou_edit", name_zh="TOCTOU编辑",
                              name_en="TOCTOU Edit", bypass_row_level_security=True)
        s.add(role); await s.flush()
        s.add(RolePermission(role_id=role.id, module="capa", permission_level=PermissionLevel.EDIT))
        await s.flush()
    user = (await s.execute(select(User).where(User.username == "test_toctou_edit"))).scalar_one_or_none()
    if user is None:
        user = User(username="test_toctou_edit", password_hash=hash_password("X@2026"),
                    display_name="TOCTOU", role_id=role.id, legacy_role="quality_engineer",
                    is_active=True, factory_id=DEFAULT_FACTORY_ID)
        s.add(user); await s.flush()
    await s.commit()
    return user, role.id


async def _cleanup_toctou(s: AsyncSession, capa_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID):
    # audit_logs first (operated_by→users FK + record_id→capa FK would otherwise block deletes)
    await s.execute(delete(AuditLog).where(
        (AuditLog.record_id == capa_id) | (AuditLog.operated_by == user_id)
    ))
    # doc-gate rows (composite FK capa_docg_* → capa_eightd) before capa delete.
    # Delete for ALL capas by this user (leftovers from prior failed runs included),
    # not just capa_id — else a stale analysis on another capa blocks the bulk delete.
    from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision
    await s.execute(text(
        "DELETE FROM capa_docg_decision WHERE analysis_id IN "
        "(SELECT a.analysis_id FROM capa_docg_analysis a "
        "JOIN capa_eightd c ON a.capa_id = c.report_id AND a.factory_id = c.factory_id "
        "WHERE c.created_by = :uid)"
    ), {"uid": user_id})
    await s.execute(text(
        "DELETE FROM capa_docg_audit WHERE analysis_id IN "
        "(SELECT a.analysis_id FROM capa_docg_analysis a "
        "JOIN capa_eightd c ON a.capa_id = c.report_id AND a.factory_id = c.factory_id "
        "WHERE c.created_by = :uid)"
    ), {"uid": user_id})
    await s.execute(text(
        "DELETE FROM capa_docg_analysis WHERE capa_id IN "
        "(SELECT report_id FROM capa_eightd WHERE created_by = :uid)"
    ), {"uid": user_id})
    await s.execute(delete(CAPAEightD).where(CAPAEightD.created_by == user_id))  # all capas by this user (incl. leftovers from prior failed runs)
    await s.execute(delete(User).where(User.user_id == user_id))
    await s.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    await s.execute(delete(RoleDefinition).where(RoleDefinition.id == role_id))
    await s.commit()


@pytest.mark.asyncio
async def test_toctou_edit_user_cannot_approve_after_concurrent_advance():
    """P1 TOCTOU（两个独立事务）：EDIT 用户在 capa=D8_GATE_PENDING 时请求 target=D8_CLOSURE
    （边无效 → 锁前按 EDIT 放行）；事务 B 先推进到 D8_APPROVAL_PENDING 并提交；事务 A 锁后
    刷新状态为 D8_APPROVAL_PENDING，(D8_APPROVAL_PENDING→D8_CLOSURE) 变合法 APPROVE 边。
    修复后 require_advance_permission 在 FOR UPDATE 锁+刷新后重做边权限校验 → EDIT 用户 403。
    （未修复时锁前 EDIT 决策成立、放行，advance_capa 越权完成审批——privilege bypass。）"""
    capa_id = None
    user_id = role_id = None
    try:
        # Setup (committed): EDIT user + capa D8_GATE_PENDING
        async with _test_session_factory() as s0:
            edit_user, role_id = await _ensure_edit_user(s0)
            user_id = edit_user.user_id
            capa = CAPAEightD(
                report_id=uuid.uuid4(), document_no=f"8D-TOCTOU-{uuid.uuid4().hex[:6]}",
                title="t", product_line_code="DC-DC-100", factory_id=DEFAULT_FACTORY_ID,
                created_by=edit_user.user_id, status="D8_GATE_PENDING", d5_correction="措施A",
                d6_verification="已验证", d7_prevention="预防",
            )
            s0.add(capa); await s0.commit()
            capa_id = capa.report_id

        # Session A (EDIT user's request): load capa stale (D8_GATE_PENDING) — pre-lock read
        async with _test_session_factory() as db_a:
            capa_a = await get_capa(db_a, capa_id)
            assert capa_a.status == "D8_GATE_PENDING"  # stale baseline

            # Session B (concurrent approver): satisfy D8 doc gate, then advance → D8_APPROVAL_PENDING + commit
            async with _test_session_factory() as db_b:
                capa_b = await get_capa(db_b, capa_id)
                # US-E2E-01.7 doc gate: need a passed decision before D8_GATE_PENDING→D8_APPROVAL_PENDING.
                await _make_done_analysis(db_b, capa_b, edit_user, [])
                await confirm_no_affected(db_b, capa_b, edit_user.user_id)
                await advance_capa(db_b, capa_b, edit_user.user_id,
                                   AdvanceRequest(target_state="D8_APPROVAL_PENDING"))
                await db_b.commit()
            # DB now D8_APPROVAL_PENDING; db_a's capa_a still stale (identity map)

            factory_a = await db_a.get(Factory, DEFAULT_FACTORY_ID)
            scope = _scope_for(edit_user, factory_a, accessible_factory_ids=None)
            # Fix: require_advance_permission locks+refreshes → fresh D8_APPROVAL_PENDING →
            # (D8_APPROVAL_PENDING→D8_CLOSURE) APPROVE edge → EDIT user 403.
            with pytest.raises(HTTPException) as exc:
                await require_advance_permission(
                    capa_id, AdvanceRequest(target_state="D8_CLOSURE"),
                    scope=scope, db=db_a,
                )
            assert exc.value.status_code == 403
            await db_a.rollback()
    finally:
        if capa_id and user_id and role_id:
            async with _test_session_factory() as sc:
                await _cleanup_toctou(sc, capa_id, user_id, role_id)