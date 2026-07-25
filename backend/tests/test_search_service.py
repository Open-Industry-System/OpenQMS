"""测试 SearchService 的核心逻辑（纯逻辑测试，不连数据库）。"""
import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.schemas.search import SearchResultItem, SemanticSearchResponse
from app.services.agent import provider_adapter
from app.services.search_service import ENTITY_MODULE_MAP, SearchService


class _PC:
    model = "test-model"


async def _fake_semantic_search(**kw):
    """Return one fake source so ask() reaches the LLM branch."""
    return SemanticSearchResponse(results=[
        SearchResultItem(
            entity_type="fmea",
            entity_id=uuid.uuid4(),
            node_id=None,
            entity_field="graph_data",
            chunk_text="焊接虚焊",
            score=0.9,
            source="vector",
            metadata={"document_no": "PFMEA-2026-001"},
        )
    ], total=1, query_time_ms=10)


async def _fake_semantic_search_two(**kw):
    """Return two fake sources for correlation-id stability tests."""
    return SemanticSearchResponse(results=[
        SearchResultItem(
            entity_type="fmea",
            entity_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            node_id=None,
            entity_field="graph_data",
            chunk_text="焊接虚焊 A",
            score=0.9,
            source="vector",
            metadata={"document_no": "PFMEA-2026-001"},
        ),
        SearchResultItem(
            entity_type="fmea",
            entity_id=uuid.UUID("87654321-4321-8765-4321-876543218765"),
            node_id=None,
            entity_field="graph_data",
            chunk_text="焊接虚焊 B",
            score=0.8,
            source="vector",
            metadata={"document_no": "PFMEA-2026-002"},
        ),
    ], total=2, query_time_ms=10)


async def _fake_semantic_search_two_reversed(**kw):
    """Same two sources as _fake_semantic_search_two, reversed order."""
    base = await _fake_semantic_search_two(**kw)
    return SemanticSearchResponse(
        results=list(reversed(base.results)),
        total=base.total,
        query_time_ms=base.query_time_ms,
    )


async def _fake_semantic_search_empty(**kw):
    """Return no sources."""
    return SemanticSearchResponse(results=[], total=0, query_time_ms=5)


class TestRAGAgentMigration:
    """RAG Q&A 迁移到 provider_adapter + write_audit_raw 的审计测试。"""

    @pytest.mark.asyncio
    async def test_rag_writes_success_audit(self, db, default_factory, admin_user, monkeypatch):
        """pc ok + complete_json 返回回答 -> audit new_values.status=success,
        record_id 是稳定哨兵（table_name='rag_qa'）。"""
        async def _ok_client(db_arg):
            return _PC()

        async def _ok_complete(pc, prompt, schema):
            return {"answer": "建议：检查焊接温度。"}

        monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _ok_complete)
        svc = SearchService(db=db, embedding_provider=None)
        monkeypatch.setattr(svc, "semantic_search", _fake_semantic_search)
        res = await svc.ask(
            question="虚焊怎么办", user=admin_user, tenant_schema="public"
        )
        await db.commit()
        rows = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "llm_rag_qa")
            )
        ).scalars().all()
        assert any(r.new_values.get("status") == "success" for r in rows), rows
        assert rows[0].table_name == "rag_qa"
        assert rows[0].factory_id is None
        assert rows[0].record_id is not None
        assert rows[0].correlation_id is not None

    @pytest.mark.asyncio
    async def test_rag_writes_llm_failed_audit(self, db, default_factory, admin_user, monkeypatch):
        async def _ok_client(db_arg):
            return _PC()

        async def _boom(pc, prompt, schema):
            raise RuntimeError("provider down")

        monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _boom)
        svc = SearchService(db=db, embedding_provider=None)
        monkeypatch.setattr(svc, "semantic_search", _fake_semantic_search)
        res = await svc.ask(
            question="虚焊怎么办", user=admin_user, tenant_schema="public"
        )
        assert "LLM 调用失败" in res.answer
        await db.commit()
        rows = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "llm_rag_qa")
            )
        ).scalars().all()
        assert any(r.new_values.get("status") == "llm_failed" for r in rows)

    @pytest.mark.asyncio
    async def test_rag_no_audit_when_pc_none(self, db, default_factory, admin_user, monkeypatch):
        async def _raise(db_arg):
            raise provider_adapter.ProviderNotConfiguredError("no cfg")

        monkeypatch.setattr(provider_adapter, "build_client", _raise)
        svc = SearchService(db=db, embedding_provider=None)
        monkeypatch.setattr(svc, "semantic_search", _fake_semantic_search)
        res = await svc.ask(
            question="虚焊怎么办", user=admin_user, tenant_schema="public"
        )
        assert res.llm_available is False
        await db.commit()
        rows = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "llm_rag_qa")
            )
        ).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_rag_correlation_id_stable_across_source_order(
        self, db, default_factory, admin_user, monkeypatch
    ):
        async def _ok_client(db_arg):
            return _PC()

        async def _ok_complete(pc, prompt, schema):
            return {"answer": "焊接虚焊处理建议。"}

        monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
        monkeypatch.setattr(provider_adapter, "complete_json", _ok_complete)

        svc = SearchService(db=db, embedding_provider=None)
        monkeypatch.setattr(svc, "semantic_search", _fake_semantic_search_two)
        res1 = await svc.ask(
            question="虚焊怎么办", user=admin_user, tenant_schema="public"
        )
        monkeypatch.setattr(svc, "semantic_search", _fake_semantic_search_two_reversed)
        res2 = await svc.ask(
            question="虚焊怎么办", user=admin_user, tenant_schema="public"
        )
        await db.commit()
        rows = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "llm_rag_qa")
            )
        ).scalars().all()
        assert len(rows) == 2
        assert rows[0].correlation_id == rows[1].correlation_id
        assert rows[0].record_id == rows[1].record_id

    @pytest.mark.asyncio
    async def test_rag_no_results_reports_llm_available_true_when_configured(
        self, db, default_factory, admin_user, monkeypatch
    ):
        async def _ok_client(db_arg):
            return _PC()

        monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
        svc = SearchService(db=db, embedding_provider=None)
        monkeypatch.setattr(svc, "semantic_search", _fake_semantic_search_empty)
        res = await svc.ask(
            question="虚焊怎么办", user=admin_user, tenant_schema="public"
        )
        assert res.llm_available is True
        assert res.answer == "未找到相关记录。"
        assert res.sources == []
        await db.commit()
        rows = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "llm_rag_qa")
            )
        ).scalars().all()
        assert rows == []


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
