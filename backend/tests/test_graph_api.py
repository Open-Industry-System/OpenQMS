import os

# 必须先设置 SECRET_KEY，否则 app.main 导入时会拒绝默认 secret
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-graph-api-tests")

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import status

from app.main import app
from app.core.deps import get_current_user
from app.api.graph import _repo


class StubGraphRepo:
    """确定性 stub，不依赖真实 PostgreSQL。
    故意在返回中加入敏感字段，用于验证 ResponseModel 白名单过滤。
    """

    async def get_cross_fmea_stats(self, product_line_code: str):
        return {
            "total_fmeas": 2,
            "total_nodes": 10,
            "node_type_distribution": {"FailureMode": 3, "Function": 2},
            "ap_distribution": {"H": 1, "M": 1, "L": 0},
            "high_ap_nodes": [
                {
                    "node_id": "n1",
                    "name": "焊接不良",
                    "ap": "H",
                    "rpn": 360,
                    "fmea_id": "fmea-1",
                    "document_no": "PFMEA-2026-001",
                    "created_by": " leaked-user-id ",
                    "updated_by": " leaked-user-id ",
                    "responsible": " leaked-name ",
                }
            ],
            "avg_rpn": 180.0,
            "top_failure_modes": [
                {"name": "焊接不良", "rpn": 360, "fmea_id": "fmea-1", "document_no": "PFMEA-2026-001"}
            ],
            "secret_field": "should-be-filtered",
        }

    async def find_similar_nodes(self, node_type, name_keyword, product_line_code, limit=20):
        return [
            {
                "node_id": "n1",
                "name": "焊接不良",
                "type": "FailureMode",
                "fmea_id": "fmea-1",
                "document_no": "PFMEA-2026-001",
                "created_by": " leaked-user-id ",
                "responsible": " leaked-name ",
            }
        ]

    async def get_impact_chain(self, fmea_id, node_id):
        return {"nodes": [], "edges": []}

    async def get_cause_chain(self, fmea_id, node_id):
        return {"nodes": [], "edges": []}


async def _override_get_current_user():
    from app.models.user import User
    return User(
        user_id="00000000-0000-0000-0000-000000000001",
        username="tester",
        display_name="测试员",
        email="tester@openqms.local",
        password_hash="hashed",
        is_active=True,
        role="admin",
    )


async def _override_repo():
    return StubGraphRepo()


@pytest.fixture
async def client():
    """基于 ASGI transport 的测试客户端，注入 stub repo 和 mock user。"""
    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[_repo] = _override_repo
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_graph_stats_product_line_required(client: AsyncClient):
    """验证 product_line_code 缺失或纯空白返回 422。"""
    resp = await client.get("/api/graph/stats")
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    resp = await client.get("/api/graph/stats?product_line_code=%20%20%20")
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_graph_similar_name_keyword_required(client: AsyncClient):
    """验证 name_keyword 纯空白返回 422。"""
    resp = await client.get(
        "/api/graph/similar?node_type=FailureMode&name_keyword=%20%20%20&product_line_code=DC-DC-100"
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_graph_stats_response_has_whitelist_fields_only(client: AsyncClient):
    """验证 stats 响应仅含白名单字段，无敏感字段外泄。"""
    resp = await client.get("/api/graph/stats?product_line_code=DC-DC-100")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert "total_fmeas" in data
    assert "ap_distribution" in data
    assert "high_ap_nodes" in data
    assert "created_by" not in data
    assert "updated_by" not in data
    assert "approved_by" not in data
    assert "secret_field" not in data
    assert "H" in data["ap_distribution"] and "M" in data["ap_distribution"] and "L" in data["ap_distribution"]
    # high_ap_nodes 中敏感字段被 ResponseModel 过滤
    first_node = data["high_ap_nodes"][0]
    assert "responsible" not in first_node
    assert "created_by" not in first_node


@pytest.mark.asyncio
async def test_graph_similar_response_has_document_no(client: AsyncClient):
    """验证 similar 响应含 document_no。"""
    resp = await client.get(
        "/api/graph/similar?node_type=FailureMode&name_keyword=焊&product_line_code=DC-DC-100"
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "document_no" in first
    assert "node_id" in first
    assert "name" in first
    # ResponseModel 白名单过滤
    assert "created_by" not in first
    assert "responsible" not in first
