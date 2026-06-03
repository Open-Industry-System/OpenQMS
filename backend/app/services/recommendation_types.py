from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class RecommendationContext:
    """上下文：当前 CAPA 数据 + 用户权限 + 预加载数据。"""
    capa_data: dict[str, Any]
    user_product_lines: list[str] | None  # None = admin 全权限
    stage: Literal["d4", "d5"]
    # 预加载的共享数据（避免每个 Source 重复查库）
    fmea_docs: list[dict[str, Any]] | None = None
    linked_fmea: dict[str, Any] | None = None


@dataclass
class RecommendationCandidate:
    """单个推荐候选。"""
    source: str  # 内部 Source 标识
    content: str  # 根因文本 / 措施文本
    category: str | None  # D5 用: "预防措施" | "探测措施" | "纠正措施"
    confidence: float
    match_reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_d4_schema(self) -> dict[str, Any]:
        """转换为 D4Recommendation 响应字典。"""
        result = {
            "failure_cause_node_id": self.metadata.get("failure_cause_node_id"),
            "failure_cause_name": self.content,
            "failure_cause_desc": self.metadata.get("failure_cause_desc"),
            "failure_mode_node_id": self.metadata.get("failure_mode_node_id"),
            "failure_mode_name": self.metadata.get("failure_mode_name"),
            "fmea_document_no": self.metadata.get("fmea_document_no"),
            "fmea_id": self.metadata.get("fmea_id"),
            # 内部 source "rule_engine" 映射为旧值 "rule"
            "match_source": "rule" if self.source == "rule_engine" else self.source,
            "match_reason": self.match_reason,
            "related_d2_keywords": self.metadata.get("related_d2_keywords", []),
            "confidence": round(self.confidence, 2),
        }
        # 历史 CAPA 来源字段（可选）
        if self.source == "historical_capa":
            result["source_capa_id"] = self.metadata.get("historical_capa_id")
            result["source_capa_document_no"] = self.metadata.get("document_no")
            result["source_product_line_code"] = self.metadata.get("product_line_code")
        return result

    def to_d5_control_schema(self) -> dict[str, Any] | None:
        """转换为 D5ExistingControl 响应字典。仅 control 类型候选可用。"""
        if self.metadata.get("control_node_id"):
            return {
                "failure_mode_node_id": self.metadata.get("failure_mode_node_id"),
                "failure_mode_name": self.metadata.get("failure_mode_name"),
                "failure_cause_node_id": self.metadata.get("failure_cause_node_id"),
                "failure_cause_name": self.metadata.get("failure_cause_name"),
                "control_node_id": self.metadata["control_node_id"],
                "control_name": self.content,
                "control_type": self.metadata.get("control_type", "prevention"),
                "match_source": "rule" if self.source == "rule_engine" else self.source,
                "match_reason": self.match_reason,
                "fmea_id": self.metadata.get("fmea_id"),
                "fmea_document_no": self.metadata.get("fmea_document_no"),
            }
        return None

    def to_d5_suggestion_schema(self) -> dict[str, Any]:
        """转换为 D5GeneralSuggestion 响应字典。"""
        result = {
            "content": self.content,
            "category": self.category or "预防措施",
            "basis": self.metadata.get("basis", ""),
            "confidence": round(self.confidence, 2),
            "match_reason": self.match_reason,
        }
        # 历史 CAPA 来源字段（可选）
        if self.source == "historical_capa":
            result["match_source"] = "historical_capa"
            result["source_capa_id"] = self.metadata.get("historical_capa_id")
            result["source_capa_document_no"] = self.metadata.get("document_no")
        return result


@dataclass
class RecommendationResult:
    """管道输出。"""
    items: list[RecommendationCandidate]
