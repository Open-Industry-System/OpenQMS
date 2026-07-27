# backend/tests/test_fmea_approval_gates.py
"""审批闭环门禁（spec「审批权限矩阵」）。

权限级别：NONE=0/VIEW=1/CREATE=2/EDIT=3/APPROVE=4/ADMIN=5。
perm_client_builder 复制自 tests/fmea/test_fmea_transition_permissions.py:34-51。
"""
import uuid
from datetime import UTC, datetime
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.fmea import FMEADocument
from app.models.role import RolePermission
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


@pytest.fixture
async def perm_client_builder(db, admin_user, default_factory):
    """工厂：按指定 fmea 权限级别构造 AsyncClient（复制自 test_fmea_transition_permissions.py）。"""
    async def _build(fmea_level: int):
        existing = (await db.execute(select(RolePermission).where(
            RolePermission.role_id == admin_user.role_id, RolePermission.module == "fmea"))).scalar_one_or_none()
        if existing is None:
            db.add(RolePermission(role_id=admin_user.role_id, module="fmea", permission_level=fmea_level))
        else:
            existing.permission_level = fmea_level
        await db.flush()
        scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_scope] = lambda: scope
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield _build
    app.dependency_overrides.clear()


async def _mk(db, factory_id, user_id, status, wizard_done=True):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-GATE-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=factory_id, status=status,
        graph_data={"nodes": [], "edges": [],
                    "wizardScope": {"wizard_completed": wizard_done}},
        version=1, created_by=user_id,
        # approved 状态的 FMEA 必须带有 approved_by/approved_at（模拟真实审批），
        # 否则 APPROVED→REWORK 的「保留 approved_by」断言无对象可守。
        approved_by=user_id if status == "approved" else None,
        approved_at=datetime.now(UTC) if status == "approved" else None,
    )
    db.add(fmea)
    await db.commit()
    return fmea


@pytest.mark.asyncio
async def test_edit_cannot_rework(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "in_review")
    client = await perm_client_builder(fmea_level=3)  # EDIT, not APPROVE
    resp = await client.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "rework", "reason": "x"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rework_requires_nonempty_reason(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "in_review")
    client = await perm_client_builder(fmea_level=4)  # APPROVE
    resp = await client.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "rework", "reason": "  "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_requires_wizard_completed(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "draft", wizard_done=False)
    client = await perm_client_builder(fmea_level=3)  # EDIT
    resp = await client.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "in_review"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_rejected_when_in_review(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "in_review")
    client = await perm_client_builder(fmea_level=3)
    resp = await client.put(f"/api/fmea/{fmea.fmea_id}", json={"title": "新标题"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_approved_to_rework_keeps_approved_by(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "approved")
    client = await perm_client_builder(fmea_level=4)
    resp = await client.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "rework", "reason": "复审"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rework"
    assert resp.json()["approved_by"] is not None  # 保留历史，不清空


@pytest.mark.asyncio
async def test_rework_reason_persisted_in_audit(perm_client_builder, db, default_factory, admin_user):
    """缺陷修复 #1：rework reason 仅校验未持久化（fmea.py:224 未传 req.reason）。
    期望：TRANSITION AuditLog.changed_fields 含 reason。"""
    from app.models.audit import AuditLog
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "in_review")
    client = await perm_client_builder(fmea_level=4)
    resp = await client.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "rework", "reason": "风险评审核改"})
    assert resp.status_code == 200
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.table_name == "fmea_documents",
        AuditLog.record_id == fmea.fmea_id,
        AuditLog.action == "TRANSITION",
    ))).scalars().all()
    assert rows, "TRANSITION audit 缺失"
    latest = rows[-1]
    assert latest.changed_fields.get("reason") == "风险评审核改", (
        f"reason 未落审计：changed_fields={latest.changed_fields}")
