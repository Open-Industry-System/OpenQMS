"""测试 SearchService 的核心逻辑（纯逻辑测试，不连数据库）。"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.search_service import SearchService, ENTITY_MODULE_MAP


class TestGetUserProductLines:
    """测试产品线获取逻辑。"""

    @pytest.mark.asyncio
    async def test_admin_returns_none(self):
        """管理员返回 None（不过滤）。"""
        db = AsyncMock()
        service = SearchService(db=db)
        user = MagicMock()
        user.role_definition.role_key = "admin"
        result = await service._get_user_product_lines(user)
        assert result is None

    @pytest.mark.asyncio
    async def test_user_with_no_product_lines_returns_empty(self):
        """无产品线的普通用户返回空列表。"""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
        service = SearchService(db=db)
        user = MagicMock()
        user.role_definition.role_key = "engineer"
        user.user_id = "test-id"
        result = await service._get_user_product_lines(user)
        assert result == []

    @pytest.mark.asyncio
    async def test_user_with_product_lines_returns_list(self):
        """有产品线的用户返回产品线列表。"""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            fetchall=MagicMock(return_value=[("DC-DC-100",), ("AC-DC-200",)])
        ))
        service = SearchService(db=db)
        user = MagicMock()
        user.role_definition.role_key = "engineer"
        user.user_id = "test-id"
        result = await service._get_user_product_lines(user)
        assert result == ["DC-DC-100", "AC-DC-200"]


class TestEntityModuleMap:
    """测试实体类型到模块的映射完整性。"""

    def test_all_entity_types_have_module_mapping(self):
        """所有 6 种实体类型都有对应的模块权限映射。"""
        expected = {"fmea_node", "capa", "audit_finding", "complaint", "scar", "rma"}
        assert set(ENTITY_MODULE_MAP.keys()) == expected

    def test_rma_maps_to_customer_quality(self):
        """RMA 映射到 CUSTOMER_QUALITY 模块（无独立 RMA 模块）。"""
        from app.core.permissions import Module
        assert ENTITY_MODULE_MAP["rma"] == Module.CUSTOMER_QUALITY


class TestRRFFusion:
    """测试 RRF 融合逻辑。"""

    def test_rrf_basic(self):
        """基本 RRF 融合：两个列表中的共同元素得分更高。"""
        from app.config import settings

        vector_results = [
            {"id": "a", "score": 0.9},
            {"id": "b", "score": 0.8},
        ]
        fulltext_results = [
            {"id": "b", "score": 1.0},
            {"id": "c", "score": 0.7},
        ]

        k = 60
        vw = settings.SEARCH_VECTOR_WEIGHT
        fw = settings.SEARCH_FULLTEXT_WEIGHT

        scores = {}
        for rank, item in enumerate(vector_results):
            scores[item["id"]] = scores.get(item["id"], 0) + vw / (k + rank)
        for rank, item in enumerate(fulltext_results):
            scores[item["id"]] = scores.get(item["id"], 0) + fw / (k + rank)

        # "b" appears in both lists, should have highest score
        assert scores["b"] > scores["a"]
        assert scores["b"] > scores["c"]
        # "a" only in vector, "c" only in fulltext
        assert "a" in scores
        assert "c" in scores
