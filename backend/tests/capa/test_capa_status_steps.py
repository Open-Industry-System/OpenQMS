"""available_steps + _STATUS_ORDER 映射测试（US-E2E-01.3）。"""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.capa import CAPAEightD
from app.models.role import RolePermission
from app.services.capa_draft_service import _STATUS_ORDER
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


@pytest.fixture
async def capa_client(db, admin_user, default_factory):
    """复制自 test_capa_verification_api.py:23（capa_client 不在 conftest，需本文件自带）。"""
    for mod, lvl in [("capa", 5), ("fmea", 5)]:
        existing = await db.execute(select(RolePermission).where(
            RolePermission.role_id == admin_user.role_id, RolePermission.module == mod))
        if existing.scalar_one_or_none() is None:
            db.add(RolePermission(role_id=admin_user.role_id, module=mod, permission_level=lvl))
    await db.flush()
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def test_status_order_contains_new_states_in_correct_sequence():
    """结构性测试：_STATUS_ORDER 在 capa_draft_service.py:43 定义但全仓未被引用
    （草稿路由用 local _STATUS_TO_STEP :345）。本测试只验结构一致性，不验草稿行为——
    行为由 test_available_steps_empty_for_shell_states 覆盖。"""
    order = {s: i for i, s in enumerate(_STATUS_ORDER)}
    assert order["D7_PREVENTION"] < order["D7_COMPLETED"]
    assert order["D7_COMPLETED"] < order["D8_GATE_PENDING"]
    assert order["D8_GATE_PENDING"] < order["D8_APPROVAL_PENDING"]
    assert order["D8_APPROVAL_PENDING"] < order["D8_CLOSURE"]


def test_status_order_includes_all_new_states():
    """结构性：_STATUS_ORDER 含 3 新状态（结构一致性，非行为驱动）。"""
    assert "D7_COMPLETED" in _STATUS_ORDER
    assert "D8_GATE_PENDING" in _STATUS_ORDER
    assert "D8_APPROVAL_PENDING" in _STATUS_ORDER


@pytest.mark.asyncio
async def test_available_steps_empty_for_shell_states(capa_client, db, default_factory, admin_user):
    """D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING → available_steps: []。
    端点为 GET /api/capa/{report_id}/draft/capabilities（capa.py:530）。"""
    for status in ("D7_COMPLETED", "D8_GATE_PENDING", "D8_APPROVAL_PENDING"):
        capa = CAPAEightD(
            report_id=uuid.uuid4(), document_no=f"8D-STEPS-{uuid.uuid4().hex[:6]}",
            title="t", product_line_code="DC-DC-100", factory_id=default_factory.id,
            created_by=admin_user.user_id, status=status, d5_correction="x",
        )
        db.add(capa); await db.flush()
        resp = await capa_client.get(f"/api/capa/{capa.report_id}/draft/capabilities")
        assert resp.status_code == 200, resp.text
        assert resp.json()["available_steps"] == [], f"{status} should have no editable steps"
