import os

# 必须先设置 SECRET_KEY，否则 app.main 导入时会拒绝默认 secret
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-graph-api-tests")

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import status

from app.main import app
from app.core.deps import get_current_user
from app.graph.deps import get_graph_repository


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

    async def get_global_stats(self):
        # 模拟跨产品线数据，故意加入敏感字段验证白名单过滤
        return {
            "total_fmeas": 5,
            "total_nodes": 50,
            "node_type_distribution": {"FailureMode": 5, "Function": 10},
            "ap_distribution": {"H": 2, "M": 2, "L": 1},
            "high_ap_nodes": [
                {
                    "node_id": "n1",
                    "name": "焊接不良",
                    "ap": "H",
                    "rpn": 360,
                    "fmea_id": "fmea-1",
                    "document_no": "PFMEA-2026-001",
                    "product_line_code": "DC-DC-100",
                    "leaked_field": "secret",
                }
            ],
            "avg_rpn": 180.0,
            "top_failure_modes": [
                {
                    "name": "密封失效",
                    "rpn": 280,
                    "fmea_id": "fmea-2",
                    "document_no": "PFMEA-2026-002",
                    "product_line_code": "DC-DC-200",
                }
            ],
        }

    async def find_similar_nodes_advanced(self, **kwargs):
        scope = kwargs.get("scope", "global")
        pl = kwargs.get("product_line_code", "DC-DC-100")
        return [
            {
                "node_id": "fm_001",
                "name": "焊接虚焊",
                "type": "FailureMode",
                "fmea_id": "fmea-1",
                "document_no": "PFMEA-2026-001",
                "product_line_code": pl,
                "product_line_name": "DC-DC 电源模块",
                "similarity_score": 0.75,
                "match_reason": "substring_match",
            }
        ]


import uuid as _uuid


def _make_user(role_key: str):
    """构造测试用的 User + RoleDefinition。"""
    from app.models.user import User
    from app.models.role import RoleDefinition
    role_id = _uuid.uuid4()
    user = User(
        user_id=_uuid.uuid4(),
        username=role_key,
        display_name=role_key,
        email=f"{role_key}@openqms.local",
        password_hash="hashed",
        is_active=True,
        role_id=role_id,
    )
    user.role_definition = RoleDefinition(
        id=role_id,
        role_key=role_key,
        name_zh=role_key,
        name_en=role_key,
        bypass_row_level_security=(role_key == "admin"),
    )
    return user


async def _override_get_current_user():
    return _make_user("admin")


async def _override_repo():
    return StubGraphRepo()


async def _override_get_user_permission(user, module, db):
    from app.core.permissions import PermissionLevel
    # admin 返回 VIEW，viewer 返回 NONE（模拟 scope 降级）
    return PermissionLevel.VIEW if user.role_definition.role_key == "admin" else PermissionLevel.NONE


@pytest.fixture
async def client():
    """基于 ASGI transport 的测试客户端，注入 stub repo 和 mock user。"""
    from app.core.permissions import get_user_permission
    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_graph_repository] = _override_repo
    app.dependency_overrides[get_user_permission] = _override_get_user_permission
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


from app.api.graph import mask_name


@pytest.mark.asyncio
async def test_global_stats_admin_only(client: AsyncClient):
    """验证 /global-stats 仅 admin 可访问。"""
    # 默认 client 使用 admin 角色，先验证 200
    resp = await client.get("/api/graph/global-stats")
    assert resp.status_code == status.HTTP_200_OK

    # 切换为 non-admin 角色
    app.dependency_overrides[get_current_user] = lambda: _make_user("viewer")
    try:
        resp = await client.get("/api/graph/global-stats")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
    finally:
        app.dependency_overrides[get_current_user] = _override_get_current_user


# mask_name 边界测试（纯函数，不依赖 HTTP）
def test_mask_name_normal():
    assert mask_name("焊接不良") == "焊接***"


def test_mask_name_short_two_chars():
    assert mask_name("短路") == "短***"


def test_mask_name_short_one_char():
    assert mask_name("A") == "A***"


def test_mask_name_empty():
    assert mask_name("") == "***"


def test_mask_name_none():
    assert mask_name(None) == "***"


def test_mask_name_non_string():
    assert mask_name(123) == "***"
    assert mask_name([1, 2, 3]) == "***"


def test_mask_name_whitespace():
    assert mask_name("   ") == "***"


def test_mask_name_two_char_alphanumeric():
    assert mask_name("A1") == "A***"


@pytest.mark.asyncio
async def test_global_stats_response_sanitized(client: AsyncClient):
    """验证 /global-stats 响应已脱敏，无敏感字段。"""
    resp = await client.get("/api/graph/global-stats")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    # 基本统计字段存在
    assert "total_fmeas" in data
    assert "ap_distribution" in data
    assert "high_ap_nodes" in data
    assert "top_failure_modes" in data

    # 敏感字段不存在
    assert "fmea_id" not in data
    assert "document_no" not in data
    assert "product_line_code" not in data
    assert "node_id" not in data
    assert "leaked_field" not in data

    # high_ap_nodes 脱敏检查
    first = data["high_ap_nodes"][0]
    assert "name" in first
    assert first["name"] == "焊接***"  # 精确值：保留前 2 字符 + ***
    assert "fmea_id" not in first
    assert "document_no" not in first
    assert "node_id" not in first
    assert "ap" in first  # high_ap_nodes 有 ap

    # top_failure_modes 脱敏检查（ap 不应出现，因为原始数据无 ap）
    top = data["top_failure_modes"][0]
    assert "name" in top
    assert top["name"] == "密封***"  # 精确值
    assert "fmea_id" not in top
    assert "document_no" not in top
    assert "ap" not in top  # response_model_exclude_none=True 过滤了 null

    # 验证原始名称未出现在任何响应字段中（防御性检查）
    raw_names = {"焊接不良", "密封失效"}
    def _check_no_raw_names(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                _check_no_raw_names(v)
        elif isinstance(obj, list):
            for item in obj:
                _check_no_raw_names(item)
        elif isinstance(obj, str):
            for raw in raw_names:
                assert raw not in obj, f"raw name '{raw}' leaked in response"
    _check_no_raw_names(data)


@pytest.mark.asyncio
async def test_global_stats_rejects_product_line_code_param(client: AsyncClient):
    """验证 /global-stats 传入 product_line_code 参数返回 400。"""
    resp = await client.get("/api/graph/global-stats?product_line_code=DC-DC-100")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_similar_nodes_advanced_success(client: AsyncClient):
    from unittest.mock import patch
    from app.core.permissions import PermissionLevel

    # 避免测试环境查询真实数据库
    with patch("app.api.graph.get_user_permission", return_value=PermissionLevel.NONE):
        resp = await client.post("/api/graph/similar-nodes", json={
            "node_type": "FailureMode",
            "query_text": "焊接",
            "scope": "global",
            "product_line_code": "DC-DC-100",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "matches" in data
    # 无 KNOWLEDGE_GRAPH 权限记录时会被降级为 current_product_line
    assert data["effective_scope"] == "current_product_line"
    assert len(data["matches"]) > 0
    first = data["matches"][0]
    assert "node_id" in first
    assert "similarity_score" in first


@pytest.mark.asyncio
async def test_similar_nodes_advanced_scope_downgrade(client: AsyncClient):
    """viewer 无 KNOWLEDGE_GRAPH 权限，global 被降级为 current_product_line。"""
    from unittest.mock import patch, AsyncMock
    from app.core.permissions import PermissionLevel

    app.dependency_overrides[get_current_user] = lambda: _make_user("viewer")
    try:
        with patch("app.api.graph.get_user_permission", return_value=PermissionLevel.NONE),              patch("app.api.graph.enforce_product_line_access", new_callable=AsyncMock):
            resp = await client.post("/api/graph/similar-nodes", json={
                "node_type": "FailureMode",
                "query_text": "焊接",
                "scope": "global",
                "product_line_code": "DC-DC-100",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["effective_scope"] == "current_product_line"
        assert len(data["matches"]) > 0
        assert data["matches"][0]["product_line_code"] == "DC-DC-100"
    finally:
        app.dependency_overrides[get_current_user] = _override_get_current_user


@pytest.mark.asyncio
async def test_similar_nodes_advanced_rejects_unauthorized_product_line(client: AsyncClient):
    """无权产品线返回 403。"""
    from unittest.mock import patch, AsyncMock
    from app.core.permissions import PermissionLevel
    from fastapi import HTTPException

    async def _raise_403(*a, **kw):
        raise HTTPException(status_code=403, detail="无权访问产品线")

    app.dependency_overrides[get_current_user] = lambda: _make_user("viewer")
    try:
        with patch("app.api.graph.get_user_permission", return_value=PermissionLevel.NONE),              patch("app.api.graph.enforce_product_line_access", side_effect=_raise_403):
            resp = await client.post("/api/graph/similar-nodes", json={
                "node_type": "FailureMode",
                "query_text": "焊接",
                "scope": "current_product_line",
                "product_line_code": "UNAUTHORIZED-PL",
            })
        assert resp.status_code == 403
    finally:
        app.dependency_overrides[get_current_user] = _override_get_current_user
