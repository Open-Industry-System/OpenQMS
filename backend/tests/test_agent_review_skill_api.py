import pytest
import uuid
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db
from app.main import app
from app.models.audit import AuditLog

pytestmark = pytest.mark.requires_db


@pytest.fixture
async def admin_client(db, admin_user, default_factory):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_admin_can_list_skills(admin_client):
    r = await admin_client.get("/api/admin/review-skills")
    assert r.status_code == 200
    names = [s["name"] for s in r.json()]
    assert "capa_ppt_review" in names


async def test_admin_can_get_skill_by_name(admin_client):
    r = await admin_client.get("/api/admin/review-skills/capa_ppt_review")
    assert r.status_code == 200
    assert r.json()["name"] == "capa_ppt_review"


async def test_admin_can_update_skill_content(admin_client):
    r = await admin_client.put(
        "/api/admin/review-skills/capa_ppt_review",
        json={"content": "updated review standard"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "updated review standard"
    assert body["version"] >= 2


async def test_reject_empty_content(admin_client):
    r = await admin_client.put(
        "/api/admin/review-skills/capa_ppt_review",
        json={"content": "   "},
    )
    assert r.status_code == 400


async def test_reject_non_default_skill_name(admin_client):
    """固定单 skill：非 capa_ppt_review 的 name -> 404（不创建新 skill）。"""
    r = await admin_client.put(
        "/api/admin/review-skills/some_other_skill",
        json={"content": "x"},
    )
    assert r.status_code == 404
    r2 = await admin_client.get("/api/admin/review-skills/some_other_skill")
    assert r2.status_code == 404


async def test_upsert_skill_writes_skill_updated_audit(admin_client, db):
    """故事 §89：admin 改 skill content 必须写 SKILL_UPDATED 审计事件。"""
    r = await admin_client.put(
        "/api/admin/review-skills/capa_ppt_review",
        json={"content": "audit-test standard"},
    )
    assert r.status_code == 200
    skill_id = uuid.UUID(r.json()["skill_id"])
    logs = (await db.execute(select(AuditLog).where(
        AuditLog.action == "SKILL_UPDATED",
        AuditLog.record_id == skill_id,
    ))).scalars().all()
    assert len(logs) >= 1, "SKILL_UPDATED 审计未写入"
    log = logs[-1]
    assert log.table_name == "agent_review_skill"
    assert log.operated_by is not None
