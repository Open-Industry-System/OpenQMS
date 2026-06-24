"""FMEAGraphRepository: 图查询抽象接口。

当前提供两个实现：
- JSONBRepository: 从 PG JSONB 读取（无需 Neo4j）
- Neo4jRepository: 从 Neo4j 读取（需要 worker 同步完成）
"""
import uuid
from abc import ABC, abstractmethod

from app.schemas.change_impact import ChangeImpactResult


class FMEAGraphRepository(ABC):
    @abstractmethod
    async def get_impact_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        """下游影响链：指定节点 → FailureEffect → Controls"""

    @abstractmethod
    async def get_cause_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        """上游原因链：指定节点 ← FailureCause"""

    @abstractmethod
    async def find_similar_nodes(
        self, node_type: str, name_keyword: str, product_line_code: str, limit: int = 20
    ) -> list[dict]:
        """跨 FMEA 搜索相似节点。product_line_code 必填。"""

    @abstractmethod
    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        """跨 FMEA 聚合统计。product_line_code 必填。"""

    @abstractmethod
    async def get_global_stats(self) -> dict:
        """跨产品线全局统计。返回结构与 get_cross_fmea_stats 相同。"""

    @abstractmethod
    async def find_similar_nodes_advanced(
        self,
        node_type: str,
        query_text: str,
        product_line_codes: list[str] | None,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        """跨 FMEA 相似节点搜索（增强版）。

        product_line_codes: None = global (no filter); a list = restrict to those codes.
        返回项包含 node_id, name, type, fmea_id, document_no, product_line_code,
        product_line_name, similarity_score, match_reason。
        """

    @abstractmethod
    async def analyze_change_impact(
        self,
        fmea_id: uuid.UUID,
        node_id: str,
        change_type: str,
        field_name: str | None,
        new_value: str | None,
    ) -> ChangeImpactResult:
        """分析变更影响范围与风险变化。"""
