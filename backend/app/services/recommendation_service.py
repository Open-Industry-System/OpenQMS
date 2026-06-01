# backend/app/services/recommendation_service.py
import hashlib
import json
import logging
import re
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select, delete, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.fmea import FMEADocument
from app.models.recommendation_cache import RecommendationCache
from app.schemas.recommendation import (
    RecommendRequest, RecommendResponse, SuggestionItem, SuggestionList,
)
from app.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule Engine (migrated from frontend/src/utils/dfmeaRules.ts)
# ---------------------------------------------------------------------------

@dataclass
class RuleSuggestion:
    name: str
    confidence: float = 0.7
    source: Literal["rule"] = "rule"
    explanation: str = ""


@dataclass
class RuleResult:
    suggestions: list[RuleSuggestion] = field(default_factory=list)
    quality: Literal["specific", "generic"] = "specific"


VERB_PATTERNS: dict[str, list[str]] = {
    "采集": ["无法采集", "采集失效", "采集精度不足", "采集延迟"],
    "收集": ["无法收集", "收集失效", "收集不完整", "收集延迟"],
    "获取": ["无法获取", "获取失效", "获取不完整", "获取延迟"],
    "传输": ["无法传输", "传输失效", "传输失真", "传输延迟"],
    "发送": ["无法发送", "发送失效", "发送失真", "发送延迟"],
    "传递": ["无法传递", "传递失效", "传递失真", "传递延迟"],
    "控制": ["无法控制", "控制失效", "控制精度不足", "控制响应慢"],
    "调节": ["无法调节", "调节失效", "调节精度不足", "调节响应慢"],
    "调控": ["无法调控", "调控失效", "调控精度不足", "调控响应慢"],
    "检测": ["无法检测", "检测失效", "检测精度不足", "误检测"],
    "监测": ["无法监测", "监测失效", "监测精度不足", "误监测"],
    "识别": ["无法识别", "识别失效", "识别精度不足", "误识别"],
    "保护": ["保护失效", "无法保护", "保护不足", "保护误动作"],
    "防护": ["防护失效", "无法防护", "防护不足", "防护误动作"],
    "隔离": ["隔离失效", "无法隔离", "隔离不足", "隔离误动作"],
    "显示": ["无法显示", "显示失效", "显示错误", "显示延迟"],
    "指示": ["无法指示", "指示失效", "指示错误", "指示延迟"],
    "反馈": ["无法反馈", "反馈失效", "反馈错误", "反馈延迟"],
    "存储": ["无法存储", "存储失效", "存储丢失", "存储容量不足"],
    "保存": ["无法保存", "保存失效", "保存丢失", "保存容量不足"],
    "记录": ["无法记录", "记录失效", "记录丢失", "记录容量不足"],
    "供电": ["无法供电", "供电失效", "供电不足", "供电不稳定"],
    "供能": ["无法供能", "供能失效", "供能不足", "供能不稳定"],
    "驱动": ["无法驱动", "驱动失效", "驱动力不足", "驱动不稳定"],
    "连接": ["连接失效", "无法连接", "连接松动", "接触不良"],
    "接合": ["接合失效", "无法接合", "接合松动", "接合不良"],
    "固定": ["固定失效", "无法固定", "固定松动", "固定不良"],
    "密封": ["密封失效", "无法密封", "密封不良", "泄漏"],
    "封闭": ["封闭失效", "无法封闭", "封闭不良", "泄漏"],
}

FAILURE_CHAIN_MAP: dict[str, dict[str, list[str]]] = {
    "无法采集": {
        "effects": ["系统数据缺失", "控制决策错误", "功能降级"],
        "causes": ["传感器故障", "信号干扰", "线路断路", "接口氧化"],
    },
    "采集精度不足": {
        "effects": ["控制偏差", "系统性能下降", "误报警"],
        "causes": ["传感器老化", "校准漂移", "温度影响", "电磁干扰"],
    },
    "无法控制": {
        "effects": ["系统失控", "设备损坏", "安全风险"],
        "causes": ["执行器故障", "控制算法缺陷", "反馈信号丢失", "电源异常"],
    },
    "密封失效": {
        "effects": ["介质泄漏", "环境污染", "设备腐蚀", "安全风险"],
        "causes": ["密封件老化", "安装不当", "材料选型错误", "温度超限"],
    },
    "连接失效": {
        "effects": ["电路断开", "信号中断", "功能丧失", "系统停机"],
        "causes": ["接触不良", "焊接缺陷", "振动疲劳", "腐蚀"],
    },
}

DEFAULT_EFFECTS = ["功能降级", "系统性能下降"]
DEFAULT_CAUSES = ["零部件老化", "环境因素", "制造缺陷"]


class RuleEngine:
    """FMEA recommendation rule engine, migrated from dfmeaRules.ts."""

    def evaluate(self, trigger_type: str, context: dict) -> RuleResult:
        dispatch = {
            "failure_mode": self._generate_failure_modes,
            "failure_effect": self._suggest_failure_effect,
            "failure_cause": self._suggest_failure_cause,
            "measure": self._suggest_measures,
            "optimization": self._suggest_optimization,
        }
        handler = dispatch.get(trigger_type)
        if not handler:
            return RuleResult(suggestions=[], quality="generic")
        return handler(context)

    def _generate_failure_modes(self, context: dict) -> RuleResult:
        func_desc = context.get("function_description", "") or context.get("input_text", "")
        if not func_desc:
            return RuleResult(suggestions=[], quality="generic")

        for verb, modes in VERB_PATTERNS.items():
            if verb in func_desc:
                return RuleResult(
                    suggestions=[RuleSuggestion(name=m, confidence=0.7, explanation=f"动词「{verb}」匹配") for m in modes],
                    quality="specific",
                )

        fallback = [f"{func_desc}失效", f"无法{func_desc}", f"{func_desc}精度不足", f"{func_desc}延迟"]
        return RuleResult(
            suggestions=[RuleSuggestion(name=m, confidence=0.4, explanation="通用否定模式") for m in fallback],
            quality="generic",
        )

    def _suggest_failure_effect(self, context: dict) -> RuleResult:
        fm = context.get("failure_mode", "")
        for key, chain in FAILURE_CHAIN_MAP.items():
            if key in fm:
                return RuleResult(
                    suggestions=[RuleSuggestion(name=e, confidence=0.7, explanation=f"关联失效模式「{key}」") for e in chain["effects"]],
                    quality="specific",
                )
        return RuleResult(
            suggestions=[RuleSuggestion(name=e, confidence=0.3, explanation="通用默认") for e in DEFAULT_EFFECTS],
            quality="generic",
        )

    def _suggest_failure_cause(self, context: dict) -> RuleResult:
        fm = context.get("failure_mode", "")
        for key, chain in FAILURE_CHAIN_MAP.items():
            if key in fm:
                return RuleResult(
                    suggestions=[RuleSuggestion(name=c, confidence=0.7, explanation=f"关联失效模式「{key}」") for c in chain["causes"]],
                    quality="specific",
                )
        return RuleResult(
            suggestions=[RuleSuggestion(name=c, confidence=0.3, explanation="通用默认") for c in DEFAULT_CAUSES],
            quality="generic",
        )

    def _suggest_measures(self, context: dict) -> RuleResult:
        fm = context.get("failure_mode", "")
        ap = context.get("ap", "L")
        prevention: list[str] = []
        detection: list[str] = []

        if ap == "H":
            prevention.extend(["冗余设计（双通道/备份）", "选用更高可靠性等级元器件", "降额设计", "失效安全设计"])
            detection.extend(["在线实时监测", "自诊断功能", "出厂100%功能测试"])
        elif ap == "M":
            prevention.extend(["优化设计参数", "增加防错结构", "选用成熟工艺"])
            detection.extend(["定期功能测试", "过程巡检", "来料检验"])
        else:
            prevention.extend(["标准化设计", "选用合格供应商物料"])
            detection.extend(["常规检验", "用户反馈跟踪"])

        if re.search(r"采集|检测|监测|识别", fm):
            prevention.extend(["传感器冗余布置", "信号滤波设计"])
            detection.extend(["传感器信号校验", "标定周期缩短"])
        if re.search(r"密封|封闭|泄漏", fm):
            prevention.extend(["双重密封结构", "密封槽优化设计"])
            detection.extend(["气密性测试", "泄漏监测"])
        if re.search(r"连接|接合|固定|接触", fm):
            prevention.extend(["防松结构设计", "镀金/镀银处理"])
            detection.extend(["接触电阻测试", "振动试验验证"])

        suggestions = (
            [RuleSuggestion(name=p, confidence=0.6, explanation="预防措施") for p in prevention]
            + [RuleSuggestion(name=d, confidence=0.6, explanation="检测措施") for d in detection]
        )
        quality: Literal["specific", "generic"] = "specific" if (fm and any(kw in fm for kw in ["采集", "密封", "连接"])) else "generic"
        return RuleResult(suggestions=suggestions, quality=quality)

    def _suggest_optimization(self, context: dict) -> RuleResult:
        s = context.get("severity", 0)
        o = context.get("occurrence", 0)
        d = context.get("detection", 0)
        ap = context.get("ap", "")

        if not ap and s and o and d:
            from app.state_machines.fmea_state import compute_ap
            ap = compute_ap(s, o, d)

        hints: list[str] = []
        if ap == "H":
            hints = ["必须采取优化措施", "建议设计变更以降低S或O", "增加冗余或提高检测能力"]
        elif ap == "M":
            hints = ["建议采取优化措施", "重点改进探测手段或降低发生度"]
        else:
            hints = ["当前风险可接受", "保持现有控制措施，持续监控"]

        return RuleResult(
            suggestions=[RuleSuggestion(name=h, confidence=0.6, explanation=f"AP={ap}") for h in hints],
            quality="specific" if ap in ("H", "M") else "generic",
        )


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

PROMPT_TEMPLATES = {
    "failure_mode": """你是一位资深质量工程师，精通 AIAG-VDA FMEA 方法论。

当前上下文：
- FMEA 类型: {fmea_type}
- 产品线: {product_line}
- 工艺步骤: {process_step}
- 功能描述: {function_description}

历史相似 FMEA 中的失败模式：
{historical_patterns}

请根据以上信息，推荐 3-5 个可能的失败模式。
要求：
1. 具体、可操作，不要泛泛而谈
2. 与当前工艺/功能直接相关
3. 参考历史数据中的真实案例

返回 JSON 格式：
{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}
""",
    "failure_effect": """你是一位资深质量工程师。当前失效模式：{failure_mode}。
请推荐 3-5 个可能的失效效应。返回 JSON：{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}""",
    "failure_cause": """你是一位资深质量工程师。当前失效模式：{failure_mode}。
请推荐 3-5 个可能的失效原因。返回 JSON：{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}""",
    "measure": """你是一位资深质量工程师。当前失效模式：{failure_mode}，AP={ap}。
请推荐预防措施和检测措施。返回 JSON：{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}""",
    "optimization": """你是一位资深质量工程师。失效模式：{failure_mode}，S={severity} O={occurrence} D={detection}。
请推荐优化行动。返回 JSON：{{"suggestions": [{{"name": "...", "confidence": 0.0-1.0, "explanation": "..."}}]}}""",
}


# ---------------------------------------------------------------------------
# Recommendation Service
# ---------------------------------------------------------------------------

class RecommendationService:
    def __init__(self, db: AsyncSession, llm_provider: LLMProvider | None):
        self.db = db
        self.llm = llm_provider
        self.rules = RuleEngine()

    async def recommend(self, fmea_id: _uuid.UUID, request: RecommendRequest) -> RecommendResponse:
        fmea = await self._get_fmea_or_404(fmea_id)

        # 1. Check cache
        context_hash = self._compute_context_hash(request.context)
        cached = await self._get_cached(fmea_id, request.trigger_type, context_hash)
        if cached:
            # Skip cache only if LLM is now available but cache was written without LLM
            # (avoids re-evaluating high-quality rule results that don't need LLM)
            if self.llm is not None and not cached.llm_available:
                pass  # fall through to re-evaluate with LLM
            else:
                return cached

        # 2. Rule engine
        rule_result = self.rules.evaluate(request.trigger_type, request.context)

        # 3. LLM if generic + available
        if rule_result.quality == "generic" and self.llm is not None:
            try:
                import asyncio
                llm_context = await self._assemble_context(fmea, request)
                prompt = self._build_prompt(request.trigger_type, llm_context)
                llm_result = await asyncio.wait_for(
                    self.llm.complete(prompt, {}),
                    timeout=settings.LLM_TIMEOUT,
                )
                validated = SuggestionList.model_validate(llm_result)
                suggestions = self._merge_suggestions(rule_result.suggestions, validated.suggestions)
                source = "hybrid"
            except Exception as e:
                suggestions = [SuggestionItem(name=s.name, confidence=s.confidence, source="rule", explanation=s.explanation) for s in rule_result.suggestions]
                source = "rule_fallback"
                logger.warning("LLM failed, falling back to rules: %s", e)
        else:
            suggestions = [SuggestionItem(name=s.name, confidence=s.confidence, source="rule", explanation=s.explanation) for s in rule_result.suggestions]
            source = "rule"

        response = RecommendResponse(
            suggestions=suggestions,
            source=source,
            cached=False,
            llm_available=self.llm is not None,
        )
        # Don't cache rule_fallback — it's a transient LLM failure, retry next time
        if source != "rule_fallback":
            await self._cache_result(fmea_id, request.trigger_type, context_hash, fmea, response)
        return response

    # -- Helpers --

    async def _get_fmea_or_404(self, fmea_id: _uuid.UUID) -> FMEADocument:
        from fastapi import HTTPException
        stmt = select(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
        result = await self.db.execute(stmt)
        fmea = result.scalar_one_or_none()
        if not fmea:
            raise HTTPException(status_code=404, detail="FMEA not found")
        return fmea

    def _compute_context_hash(self, context: dict) -> str:
        raw = json.dumps(context, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    async def _get_cached(self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str) -> RecommendResponse | None:
        stmt = (
            select(RecommendationCache)
            .where(RecommendationCache.fmea_id == fmea_id)
            .where(RecommendationCache.trigger_type == trigger_type)
            .where(RecommendationCache.context_hash == context_hash)
            .where(RecommendationCache.expires_at > func.now())
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            # Use the cached llm_available flag to determine if cache was written with LLM context
            # The current self.llm state is used for the response, but the cached flag is stored separately
            return RecommendResponse(
                suggestions=row.suggestions,
                source=row.source,
                cached=True,
                llm_available=getattr(row, "llm_available", False),
            )
        return None

    async def _cache_result(
        self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str,
        fmea: FMEADocument, response: RecommendResponse,
    ) -> None:
        stmt = (
            pg_insert(RecommendationCache)
            .values(
                fmea_id=fmea_id,
                trigger_type=trigger_type,
                context_hash=context_hash,
                product_line_code=fmea.product_line_code,
                fmea_type=fmea.fmea_type,
                suggestions=[s.model_dump() for s in response.suggestions],
                source=response.source,
                llm_available=self.llm is not None,
            )
            .on_conflict_do_update(
                index_elements=["fmea_id", "trigger_type", "context_hash"],
                set_={
                    "suggestions": [s.model_dump() for s in response.suggestions],
                    "source": response.source,
                    "llm_available": self.llm is not None,
                    "product_line_code": fmea.product_line_code,
                    "fmea_type": fmea.fmea_type,
                    "created_at": func.now(),
                    "expires_at": func.now() + text("INTERVAL '24 hours'"),
                },
            )
        )
        await self.db.execute(stmt)

    async def invalidate_cache_for_fmea(self, fmea_id: _uuid.UUID) -> None:
        await self.db.execute(
            delete(RecommendationCache).where(RecommendationCache.fmea_id == fmea_id)
        )

    async def _assemble_context(self, fmea: FMEADocument, request: RecommendRequest) -> dict:
        historical = await self._get_similar_fmeas(fmea)
        return {
            "fmea_type": fmea.fmea_type,
            "product_line": fmea.product_line_code,
            "current_context": request.context,
            "historical_patterns": self._extract_patterns(historical),
        }

    async def _get_similar_fmeas(self, fmea: FMEADocument, limit: int = 5) -> list[FMEADocument]:
        stmt = (
            select(FMEADocument)
            .where(FMEADocument.fmea_type == fmea.fmea_type)
            .where(FMEADocument.product_line_code == fmea.product_line_code)
            .where(FMEADocument.status == "approved")
            .where(FMEADocument.fmea_id != fmea.fmea_id)
            .order_by(FMEADocument.updated_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _extract_patterns(self, fmeas: list[FMEADocument]) -> list[dict]:
        patterns = []
        for fmea in fmeas:
            nodes = fmea.graph_data.get("nodes", [])
            edges = fmea.graph_data.get("edges", [])
            for node in nodes:
                if node.get("type") == "FailureMode":
                    effects = [n["name"] for n in nodes if n["type"] == "FailureEffect"
                               and any(e["source"] == node["id"] and e["target"] == n["id"] for e in edges if e["type"] == "EFFECT_OF")]
                    causes = [n["name"] for n in nodes if n["type"] == "FailureCause"
                              and any(e["source"] == n["id"] and e["target"] == node["id"] for e in edges if e["type"] == "CAUSE_OF")]
                    patterns.append({"failure_mode": node["name"], "effects": effects, "causes": causes, "source_doc": fmea.document_no})
        return patterns

    def _build_prompt(self, trigger_type: str, context: dict) -> str:
        template = PROMPT_TEMPLATES.get(trigger_type, "")
        safe = {k: v for k, v in context.get("current_context", {}).items()}
        safe.update({k: v for k, v in context.items() if k != "current_context"})
        safe["historical_patterns"] = json.dumps(context.get("historical_patterns", []), ensure_ascii=False)
        try:
            return template.format(**safe)
        except KeyError:
            return template

    def _merge_suggestions(self, rule_suggestions: list[RuleSuggestion], llm_suggestions: list[SuggestionItem]) -> list[SuggestionItem]:
        seen = {s.name for s in rule_suggestions}
        merged = [SuggestionItem(name=s.name, confidence=s.confidence, source="rule", explanation=s.explanation) for s in rule_suggestions]
        for s in llm_suggestions:
            if s.name not in seen:
                merged.append(SuggestionItem(name=s.name, confidence=s.confidence, source="llm", explanation=s.explanation))
                seen.add(s.name)
        return merged
