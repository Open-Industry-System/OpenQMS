import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import uuid
from unittest.mock import patch

import pytest

from app.core.permissions import PermissionLevel
from app.models.fmea import FMEADocument
from app.schemas.recommendation import RecommendRequest
from app.services.product_line_service import create_product_line
from app.services.product_type_service import create_product_type
from app.services.recommendation_service import RecommendationService


@pytest.mark.asyncio
async def test_recommend_current_product_type_passes_sibling_codes(db, default_factory, admin_user, request_scope_all):
    """current_product_type scope 应将同产品类型下的兄弟产品线代码透传给 graph repo。

    使用 PT-* 前缀的唯一代码（admin_user fixture 预创建了 DC-DC-100），
    用一个捕获 kwargs 的 fake graph_repo 断言 product_line_codes 集合。
    """
    # Seed a product type + two sibling product lines under POWER
    await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
    await create_product_line(db, "PT-DC-100", "DC-DC 100W", factory_id=default_factory.id, product_type_code="POWER")
    await create_product_line(db, "PT-AC-200", "AC-DC 200W", factory_id=default_factory.id, product_type_code="POWER")

    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no="PFMEA-PT-1",
        title="PT test",
        fmea_type="PFMEA",
        product_line_code="PT-DC-100",
        status="draft",
        version=1,
        graph_data={"nodes": [], "edges": []},
        lock_version=1,
        factory_id=default_factory.id,
        created_by=admin_user.user_id,
    )
    db.add(fmea)
    await db.commit()

    captured: dict = {}

    class _FakeRepo:
        async def find_similar_nodes_advanced(self, **kwargs):
            captured.update(kwargs)
            return []

    fake_repo = _FakeRepo()

    service = RecommendationService(db=db, llm_provider=None, graph_repo=fake_repo)
    req = RecommendRequest(
        trigger_type="failure_mode",
        context={"function_description": "采集单体电压"},
        scope="current_product_type",
    )
    # Admin's KG VIEW permission is normally migration-seeded (029_knowledge_graph_permissions);
    # destructive tests that drop_all+create_all wipe that row, so establish the precondition
    # explicitly rather than depend on seed data surviving.
    with patch("app.core.permissions.get_user_permission", return_value=PermissionLevel.VIEW):
        await service.recommend(fmea.fmea_id, req, admin_user, request_scope_all)

    assert set(captured["product_line_codes"]) == {"PT-DC-100", "PT-AC-200"}
    # scope/product_line_code kwargs must NOT be passed (unified signature)
    assert "scope" not in captured
    assert "product_line_code" not in captured


@pytest.mark.asyncio
async def test_recommend_no_kg_current_product_type_downgrades_to_current_product_line(db, default_factory, admin_user, request_scope_all):
    """无 KG VIEW 权限 + scope=current_product_type → 强制降级到 current_product_line。

    用 fake graph_repo 捕获传给 find_similar_nodes_advanced 的 product_line_codes，
    必须只有当前产品线 PT-DC-100（不包含兄弟 PT-AC-200）。
    """
    await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
    await create_product_line(db, "PT-DC-100", "DC-DC 100W", factory_id=default_factory.id, product_type_code="POWER")
    await create_product_line(db, "PT-AC-200", "AC-DC 200W", factory_id=default_factory.id, product_type_code="POWER")

    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no="PFMEA-PT-2",
        title="PT no-KG test",
        fmea_type="PFMEA",
        product_line_code="PT-DC-100",
        status="draft",
        version=1,
        graph_data={"nodes": [], "edges": []},
        lock_version=1,
        factory_id=default_factory.id,
        created_by=admin_user.user_id,
    )
    db.add(fmea)
    await db.commit()

    captured: dict = {}

    class _FakeRepo:
        async def find_similar_nodes_advanced(self, **kwargs):
            captured.update(kwargs)
            return []

    fake_repo = _FakeRepo()
    service = RecommendationService(db=db, llm_provider=None, graph_repo=fake_repo)
    req = RecommendRequest(
        trigger_type="failure_mode",
        context={"function_description": "采集单体电压"},
        scope="current_product_type",
    )

    with patch("app.core.permissions.get_user_permission", return_value=PermissionLevel.NONE):
        await service.recommend(fmea.fmea_id, req, admin_user, request_scope_all)

    assert captured.get("product_line_codes") == ["PT-DC-100"]
    assert "scope" not in captured
    assert "product_line_code" not in captured