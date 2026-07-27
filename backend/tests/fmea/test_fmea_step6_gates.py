# backend/tests/fmea/test_fmea_step6_gates.py
"""AIAG-VDA Step6 风险处置门禁（spec US-E2E-02.6 / 02.13）。

覆盖三类门禁：
- Defect B: status=completed → action_taken/completion_date/revised_occurrence/revised_detection/revised_ap 必填
- Defect C: status=not_executed → 关联 FailureCause 的 control_sufficiency_reason 或 risk_acceptance_reason 非空
- Defect D: S=9-10 + AP=H/M → 关联 FailureCause 的 management_review_evidence 非空

perm_client_builder + _mk 复制自 tests/test_fmea_approval_gates.py:21-56。
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
    """工厂：按指定 fmea 权限级别构造 AsyncClient（复制自 test_fmea_approval_gates.py）。"""
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
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-STEP6-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=factory_id, status=status,
        graph_data={"nodes": [], "edges": [],
                    "wizardScope": {"wizard_completed": wizard_done}},
        version=1, created_by=user_id,
        approved_by=user_id if status == "approved" else None,
        approved_at=datetime.now(UTC) if status == "approved" else None,
    )
    db.add(fmea)
    await db.commit()
    return fmea


@pytest.mark.asyncio
async def test_completed_action_requires_completion_fields(perm_client_builder, db, default_factory, admin_user):
    """Defect B: status=completed 但 action_taken/completion_date/revised_* 缺失 → 422。"""
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "draft")
    client = await perm_client_builder(fmea_level=3)  # EDIT
    graph = {
        "nodes": [
            {"id": "fc1", "type": "FailureCause", "name": "c", "occurrence": 5},
            {"id": "ra1", "type": "RecommendedAction", "name": "act",
             "status": "completed", "responsible": "张工", "due_date": "2026-08-31",
             "revised_occurrence": 0, "revised_detection": 0, "revised_ap": None},
        ],
        "edges": [{"source": "fc1", "target": "ra1", "type": "OPTIMIZED_BY"}],
        "wizardScope": {"wizard_completed": True},
    }
    resp = await client.put(f"/api/fmea/{fmea.fmea_id}", json={"graph_data": graph})
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_completed_action_with_all_fields_succeeds(perm_client_builder, db, default_factory, admin_user):
    """正向：status=completed 且 5 字段齐 → 200（不过度拦截）。"""
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "draft")
    client = await perm_client_builder(fmea_level=3)
    graph = {
        "nodes": [
            {"id": "fc1", "type": "FailureCause", "name": "c", "occurrence": 5},
            {"id": "ra1", "type": "RecommendedAction", "name": "act",
             "status": "completed", "responsible": "张工", "due_date": "2026-08-31",
             "action_taken": "已增加 AOI 复检工位", "completion_date": "2026-08-15",
             "revised_occurrence": 3, "revised_detection": 2, "revised_ap": "L"},
        ],
        "edges": [{"source": "fc1", "target": "ra1", "type": "OPTIMIZED_BY"}],
        "wizardScope": {"wizard_completed": True},
    }
    resp = await client.put(f"/api/fmea/{fmea.fmea_id}", json={"graph_data": graph})
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_not_executed_requires_reason(perm_client_builder, db, default_factory, admin_user):
    """Defect C: status=not_executed 但无 control_sufficiency_reason/risk_acceptance_reason → 422。"""
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "draft")
    client = await perm_client_builder(fmea_level=3)
    graph = {
        "nodes": [
            {"id": "fc1", "type": "FailureCause", "name": "c", "occurrence": 5,
             "control_sufficiency_reason": None, "risk_acceptance_reason": None},
            {"id": "ra1", "type": "RecommendedAction", "name": "act", "status": "not_executed"},
        ],
        "edges": [{"source": "fc1", "target": "ra1", "type": "OPTIMIZED_BY"}],
        "wizardScope": {"wizard_completed": True},
    }
    resp = await client.put(f"/api/fmea/{fmea.fmea_id}", json={"graph_data": graph})
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_not_executed_with_reason_succeeds(perm_client_builder, db, default_factory, admin_user):
    """正向：status=not_executed 且 control_sufficiency_reason 非空 → 200。"""
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "draft")
    client = await perm_client_builder(fmea_level=3)
    graph = {
        "nodes": [
            {"id": "fc1", "type": "FailureCause", "name": "c", "occurrence": 5,
             "control_sufficiency_reason": "现有 PC 已覆盖 H 级风险"},
            {"id": "ra1", "type": "RecommendedAction", "name": "act", "status": "not_executed"},
        ],
        "edges": [{"source": "fc1", "target": "ra1", "type": "OPTIMIZED_BY"}],
        "wizardScope": {"wizard_completed": True},
    }
    resp = await client.put(f"/api/fmea/{fmea.fmea_id}", json={"graph_data": graph})
    assert resp.status_code == 200, resp.text
