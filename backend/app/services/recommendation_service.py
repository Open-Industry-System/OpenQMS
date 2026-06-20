# backend/app/services/recommendation_service.py
import hashlib
import json
import logging
import re
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.graph.repository import FMEAGraphRepository
from app.models.fmea import FMEADocument
from app.models.recommendation_cache import RecommendationCache
from app.models.user import User
from app.schemas.recommendation import (
    RecommendRequest,
    RecommendResponse,
    SuggestionItem,
    SuggestionList,
)
from app.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# _NullGraphRepo — 用于不依赖 graph 查询的场景（如 cache invalidation）
# ---------------------------------------------------------------------------

class _NullGraphRepo(FMEAGraphRepository):
    """仅用于 cache invalidation 等不依赖 graph 查询的场景。"""
    async def get_impact_chain(self, *a, **kw): return {"nodes": [], "edges": []}
    async def get_cause_chain(self, *a, **kw): return {"nodes": [], "edges": []}
    async def find_similar_nodes(self, *a, **kw): return []
    async def get_cross_fmea_stats(self, *a, **kw): return {}
    async def get_global_stats(self): return {}
    async def analyze_change_impact(self, *a, **kw):
        from app.schemas.change_impact import ChangeImpactResult, ImpactSummary
        return ChangeImpactResult(affected_nodes=[], summary=ImpactSummary(
            total_affected=0, failure_modes_affected=0, controls_affected=0,
            ap_upgraded_count=0, max_hop_distance=0,
        ))
    async def find_similar_nodes_advanced(self, *a, **kw): return []


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
            quality="generic",
        )


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

PROMPT_TEMPLATES = {
    "failure_mode": """你是资深质量工程师，精通 AIAG-VDA FMEA 方法论。

【任务】为下方功能/工艺推荐 3-5 个「失效模式(FM)」。
【FM 定义】功能未能按预期实现的方式。用技术术语描述，类型包括：功能丧失、功能退化、功能间歇、部分功能丧失、非预期功能、功能超范围、功能延迟。
【方向约束】FM 描述的是"功能怎么坏了"，不是"后果(效应)"也不是"为什么坏(原因)"。

【当前上下文】
- FMEA 类型: {fmea_type}（DFMEA=设计, PFMEA=过程）
- 产品线: {product_line}
- 工艺步骤/结构要素: {process_step}
- 功能描述: {function_description}

【历史相似案例】
{historical_patterns}

【示例（功能=采集单体电压）】
失效模式: 采集精度不足 / 采集间歇中断 / 采集值漂移 / 无法采集

【要求】具体、可操作、与当前功能直接相关，参考历史案例但不要照抄不相关的。
返回 JSON：
{{"suggestions": [{{"name": "失效模式描述", "confidence": 0.0-1.0, "explanation": "为何这是合理的失效模式"}}]}}
""",
    "failure_effect": """你是资深质量工程师，精通 AIAG-VDA FMEA 方法论。

【任务】为下方失效模式推荐 3-5 个「失效效应(FE)」。
【FE 定义】失效模式产生的【后果】，描述对下一级集成产品、最终用户、法规的影响——即"用户/下游会注意到什么、体验到什么"。可含安全影响。一个 FM 可有多个 FE。
【方向约束】FE 必须是失效的【后果】，不是失效本身、不是功能、更不是失效【原因】。
  - 正确(效应): 密封泄漏导致介质外泄、焊缝强度下降引发断裂、控制决策偏差
  - 错误(这些是原因，禁止输出): 密封件老化、传感器故障、扭矩不足、校准漂移

【当前上下文】
- FMEA 类型: {fmea_type}
- 失效模式: {failure_mode}
- 功能描述: {function_description}

【示例（失效模式=焊缝气孔）】
失效效应: 焊缝承载强度下降 / 介质泄漏引发安全风险 / 疲劳寿命缩短 / 应力集中导致裂纹扩展

【要求】针对该失效模式的具体后果，避免"功能降级""性能下降"等空泛表述。
返回 JSON：
{{"suggestions": [{{"name": "失效效应描述", "confidence": 0.0-1.0, "explanation": "为何这是该失效模式的后果"}}]}}
""",
    "failure_cause": """你是资深质量工程师，精通 AIAG-VDA FMEA 方法论。

【任务】为下方失效模式推荐 3-5 个「失效原因(FC)」。
【FC 定义】失效模式【为什么会发生】的根本起因。来源：功能/性能设计不当、系统交互、随时间变化(疲劳/磨损/腐蚀/老化)、外部环境、制造/装配工艺、用户误操作、个体变化、软件问题。
【方向约束】FC 必须是失效的【起因】，不是失效本身、不是功能、更不是失效【后果/效应】。
  - 正确(原因): 密封件老化、传感器校准漂移、焊接电流不足、扭矩超差
  - 错误(这些是效应，禁止输出): 介质泄漏、系统停机、安全风险、功能丧失

【当前上下文】
- FMEA 类型: {fmea_type}
- 失效模式: {failure_mode}
- 功能描述: {function_description}

【示例（失效模式=焊缝气孔）】
失效原因: 焊接电流不足 / 保护气体流量偏低 / 母材表面油污未清理 / 焊接速度过快

【要求】针对该失效模式的具体可追溯起因，便于据此采取预防/检测措施，避免"环境因素""制造缺陷"等空泛表述。
返回 JSON：
{{"suggestions": [{{"name": "失效原因描述", "confidence": 0.0-1.0, "explanation": "为何这会引发该失效模式"}}]}}
""",
    "measure": """你是资深质量工程师，精通 AIAG-VDA FMEA 方法论。

【任务】为下方失效模式推荐 3-5 个「措施」，区分预防控制(P)与探测控制(D)。
【预防控制(P)】阻止失效模式或失效原因发生的设计/工艺手段（防止"发生"或"起因"）。
【探测控制(D)】在交付前探测失效模式或失效原因的检验/测试手段（探测"已发生"或"已起因"）。
【方向约束】措施必须可执行、可验证，与该失效模式直接相关。

【当前上下文】
- FMEA 类型: {fmea_type}
- 失效模式: {failure_mode}
- AP(行动优先级): {ap}

【示例（失效模式=焊缝气孔, AP=H）】
P: 焊接参数(电流/气流量)在线监控与闭环 / 焊前母材清洁度自动检验
D: 焊后100% X射线探伤 / 焊缝气密性在线检测

【要求】在 name 中用前缀「P:」或「D:」标注类型；explanation 说明为何针对该失效。
返回 JSON：
{{"suggestions": [{{"name": "P: 措施描述 或 D: 措施描述", "confidence": 0.0-1.0, "explanation": "为何针对该失效模式及为何属预防/探测"}}]}}
""",
    "optimization": """你是资深质量工程师，精通 AIAG-VDA FMEA 方法论。

【任务】针对下方高风险失效模式，推荐 3-5 个「优化行动」，以降低风险。
【优化行动】具体可执行的改进措施，目标是在 S(严重度)、O(频度)、D(探测度) 中至少一项上取得可量化改善，或明确职责与时限。
【方向约束】行动须具体、可分配、可追踪，避免"加强管理""提高意识"等空泛表述。

【当前上下文】
- FMEA 类型: {fmea_type}
- 失效模式: {failure_mode}
- S(严重度)={severity}  O(频度)={occurrence}  D(探测度)={detection}

【示例（失效模式=焊缝气孔, S=8 O=5 D=6）】
优化行动: 引入焊接参数自适应闭环控制以降低O / 焊后增加X射线100%探伤工位以改善D / 更换低气孔倾向焊材以降低O

【要求】每条 explanation 说明改善的是 S/O/D 中的哪一项及预期方向。
返回 JSON：
{{"suggestions": [{{"name": "优化行动描述", "confidence": 0.0-1.0, "explanation": "改善S/O/D中哪项及如何改善"}}]}}
""",
    "dfmea_tool": """你是资深DFMEA(设计FMEA)工程师，精通AIAG-VDA方法论。

【任务】为下方DFMEA分析推荐 3-5 个合适的「分析工具/方法」。
【工具定义】用于结构/功能/接口/失效分析的方法与图样，例如边界图、P图(参数图)、接口矩阵、功能分析、故障树(FTA)等。
【方向约束】推荐具体、可执行的方法或图样名称，不要泛泛的"质量工具"。

【当前上下文】
- FMEA 标题: {fmea_title}
- 产品线: {product_line_code}
- 分析任务: {task}
- 团队: {team}

【历史相似案例】
{historical_patterns}

【示例】分析工具: 边界图 / P图(参数图) / 接口矩阵 / 功能分析 / 故障树分析(FTA)

【要求】与当前任务/产品直接相关，便于据此开展结构分析与功能分析。
返回 JSON：
{{"suggestions": [{{"name": "工具/方法名称", "confidence": 0.0-1.0, "explanation": "为何适合当前DFMEA分析"}}]}}
""",
    "dfmea_trend": """你是资深DFMEA(设计FMEA)工程师，精通AIAG-VDA方法论。

【任务】为下方DFMEA分析推荐 3-5 个「趋势数据/信息源」。
【趋势定义】指导本次分析的输入信息与历史数据来源，例如历史FMEA、售后/现场故障数据、客户投诉、CAPA记录、召回/法规数据等。
【方向约束】推荐具体的数据源类别，便于据此收集分析输入。

【当前上下文】
- FMEA 标题: {fmea_title}
- 产品线: {product_line_code}
- 分析任务: {task}
- 团队: {team}

【历史相似案例】
{historical_patterns}

【示例】趋势数据: 历史FMEA / 售后现场故障数据 / 客户投诉 / CAPA记录 / 召回法规数据

【要求】与当前产品线/任务相关、能指导风险识别的数据源。
返回 JSON：
{{"suggestions": [{{"name": "趋势数据/信息源", "confidence": 0.0-1.0, "explanation": "为何该数据源对本次分析有价值"}}]}}
""",
}


# ---------------------------------------------------------------------------
# Recommendation Service
# ---------------------------------------------------------------------------

class RecommendationService:
    def __init__(self, db: AsyncSession, llm_provider: LLMProvider | None, graph_repo: FMEAGraphRepository, llm_timeout: int | None = None):
        self.db = db
        self.llm = llm_provider
        self.graph_repo = graph_repo
        self.rules = RuleEngine()
        # FMEA prompts on OpenAI-compatible gateways can take ~9s; keep a
        # safe lower bound so configured providers don't look unavailable.
        self.llm_timeout = max(llm_timeout or settings.LLM_TIMEOUT, 15)

    async def recommend(self, fmea_id: _uuid.UUID, request: RecommendRequest, user: User) -> RecommendResponse:
        from app.core.permissions import Module, PermissionLevel, get_user_permission

        fmea = await self._get_fmea_or_404(fmea_id)

        # 权限检查 + scope 强制降级
        requested_scope = getattr(request, "scope", "global")
        has_kg_permission = await get_user_permission(user, Module.KNOWLEDGE_GRAPH, self.db) >= PermissionLevel.VIEW
        effective_scope = "current_product_line" if (not has_kg_permission and requested_scope == "global") else requested_scope
        include_graph = getattr(request, "include_graph", True)

        # 1. Check cache（cache key 包含 scope 和 include_graph）
        context_hash = self._compute_context_hash({
            **request.context,
            "scope": effective_scope,
            "include_graph": include_graph,
        })
        cache_result = await self._get_cached(
            fmea_id, request.trigger_type, context_hash, effective_scope
        )
        if cache_result:
            cached_response, cached_with_llm = cache_result
            if self.llm is not None and not cached_with_llm:
                pass  # fall through to re-evaluate with LLM
            else:
                return cached_response

        # 2. Rule engine（sync, ~1ms）
        rule_result = self.rules.evaluate(request.trigger_type, request.context)
        rule_suggestions = [
            SuggestionItem(name=s.name, confidence=s.confidence, source="rule", explanation=s.explanation)
            for s in rule_result.suggestions
        ]

        # 3. Graph similarity query
        graph_suggestions: list[SuggestionItem] = []
        if include_graph:
            try:
                graph_matches = await self._query_graph_similarity(
                    fmea, request.trigger_type, request.context, effective_scope
                )
                graph_suggestions = self._graph_matches_to_suggestions(
                    graph_matches, fmea.product_line_code
                )
            except Exception as e:
                logger.warning("Graph similarity query failed: %s", e)

        # 4. Merge & deduplicate
        all_suggestions = self._merge_and_deduplicate(rule_suggestions, graph_suggestions)

        # 5. Determine if LLM is needed
        need_llm = self._need_llm(
            llm_available=self.llm is not None,
            has_specific=any(s.confidence >= 0.6 for s in all_suggestions),
            suggestion_count=len(all_suggestions),
            rule_quality=rule_result.quality,
        )

        if need_llm:
            try:
                import asyncio
                llm_context = await self._assemble_context(fmea, request)
                if graph_suggestions:
                    llm_context["similar_history"] = [
                        {"name": s.name, "from": s.source_document_no}
                        for s in graph_suggestions[:5]
                    ]
                prompt = self._build_prompt(request.trigger_type, llm_context)
                llm_result = await asyncio.wait_for(
                    self.llm.complete(prompt, {}),
                    timeout=self.llm_timeout,
                )
                validated = SuggestionList.model_validate(llm_result)
                llm_items = [
                    SuggestionItem(
                        name=s.name, confidence=s.confidence, source="llm", explanation=s.explanation
                    )
                    for s in validated.suggestions
                ]
                all_suggestions = self._merge_and_deduplicate(all_suggestions, llm_items)
                source = "graph_enriched" if graph_suggestions else "hybrid"
            except Exception as e:
                source = "graph" if graph_suggestions else "rule_fallback"
                logger.warning("LLM failed, using rule+graph results: %s: %r", type(e).__name__, e)
        else:
            source = "graph" if graph_suggestions else "rule"

        response = RecommendResponse(
            suggestions=all_suggestions[:10],
            source=source,
            cached=False,
            llm_available=self.llm is not None,
            graph_match_count=len(graph_suggestions),
            effective_scope=effective_scope,
        )

        if source != "rule_fallback":
            await self._cache_result(fmea_id, request.trigger_type, context_hash, fmea, response)
        return response

    # -- Graph similarity methods --

    async def _query_graph_similarity(
        self, fmea: FMEADocument, trigger_type: str, context: dict, scope: str
    ) -> list[dict]:
        query_text = ""
        if trigger_type == "failure_mode":
            query_text = context.get("function_description") or context.get("input_text") or ""
        else:
            query_text = context.get("failure_mode") or ""

        if not query_text or len(query_text) < 2:
            return []

        fm_matches = await self.graph_repo.find_similar_nodes_advanced(
            node_type="FailureMode",
            query_text=query_text,
            scope=scope,
            product_line_code=fmea.product_line_code,
            limit=20,
            min_similarity=0.3,
        )

        if trigger_type == "failure_mode":
            return fm_matches

        recommendations = []
        for match in fm_matches:
            neighbors = await self._extract_neighbors_from_match(match, trigger_type)
            for n in neighbors:
                recommendations.append({
                    "node_id": n.get("id", ""),
                    "name": n.get("name", ""),
                    "type": n.get("type", ""),
                    "fmea_id": match["fmea_id"],
                    "document_no": match["document_no"],
                    "product_line_code": match["product_line_code"],
                    "product_line_name": match.get("product_line_name", match["product_line_code"]),
                    "similarity_score": match["similarity_score"],
                    "match_reason": f"{match['match_reason']}_neighbor",
                    "parent_node_name": match["name"],
                })
        return recommendations

    async def _extract_neighbors_from_match(self, match: dict, trigger_type: str) -> list[dict]:
        fmea_id = _uuid.UUID(match["fmea_id"])
        graph_data = await self._get_graph_data_by_fmea_id(fmea_id)
        if not graph_data:
            return []

        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        node_map = {n["id"]: n for n in nodes}
        fm_id = match["node_id"]

        if trigger_type == "failure_effect":
            return [
                node_map[e["target"]] for e in edges
                if e.get("type") == "EFFECT_OF" and e.get("source") == fm_id
                and e.get("target") in node_map
            ]

        elif trigger_type == "failure_cause":
            return [
                node_map[e["source"]] for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
                and e.get("source") in node_map
            ]

        elif trigger_type == "measure":
            ctrl_ids = set()
            for e in edges:
                if e.get("type") in ("PREVENTED_BY", "DETECTED_BY") and e.get("source") == fm_id:
                    ctrl_ids.add(e.get("target"))
            cause_ids = {
                e.get("source") for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
            }
            for e in edges:
                if e.get("type") in ("PREVENTED_BY", "DETECTED_BY") and e.get("source") in cause_ids:
                    ctrl_ids.add(e.get("target"))
            return [node_map[cid] for cid in ctrl_ids if cid in node_map]

        elif trigger_type == "optimization":
            opt_ids = set()
            for e in edges:
                if e.get("type") == "OPTIMIZED_BY" and e.get("source") == fm_id:
                    opt_ids.add(e.get("target"))
            cause_ids = {
                e.get("source") for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
            }
            for e in edges:
                if e.get("type") == "OPTIMIZED_BY" and e.get("source") in cause_ids:
                    opt_ids.add(e.get("target"))
            return [node_map[oid] for oid in opt_ids if oid in node_map]

        return []

    async def _get_graph_data_by_fmea_id(self, fmea_id: _uuid.UUID) -> dict | None:
        from sqlalchemy import select as sa_select
        result = await self.db.execute(
            sa_select(FMEADocument.graph_data).where(FMEADocument.fmea_id == fmea_id)
        )
        row = result.scalar_one_or_none()
        return row if row else None

    def _graph_matches_to_suggestions(
        self, matches: list[dict], current_product_line_code: str
    ) -> list[SuggestionItem]:
        suggestions = []
        for m in matches:
            confidence = 0.5 + (m.get("similarity_score", 0) * 0.5)
            if m.get("parent_node_name"):
                explanation = f"来自相似失效模式「{m['parent_node_name']}」的{m.get('type', '节点')}"
            else:
                explanation = f"历史相似节点（{m.get('match_reason', '')}）"

            suggestions.append(SuggestionItem(
                name=m["name"],
                confidence=round(confidence, 2),
                source="graph",
                explanation=explanation,
                source_fmea_id=m.get("fmea_id"),
                source_document_no=m.get("document_no"),
                source_product_line_code=m.get("product_line_code"),
                source_product_line_name=m.get("product_line_name", m.get("product_line_code")),
                source_node_type=m.get("type"),
                source_node_id=m.get("node_id"),
                similarity_score=m.get("similarity_score"),
                match_reason=m.get("match_reason"),
            ))
        return suggestions

    def _merge_and_deduplicate(
        self,
        items_a: list[SuggestionItem],
        items_b: list[SuggestionItem],
    ) -> list[SuggestionItem]:
        seen: dict[str, SuggestionItem] = {}
        for item in items_a:
            key = item.name.strip()
            seen[key] = item
        for item in items_b:
            key = item.name.strip()
            existing = seen.get(key)
            if existing is None or item.confidence > existing.confidence or item.confidence == existing.confidence and item.source == "graph" and existing.source != "graph":
                seen[key] = item
        return sorted(seen.values(), key=lambda x: x.confidence, reverse=True)

    @staticmethod
    def _need_llm(
        llm_available: bool,
        has_specific: bool,
        suggestion_count: int,
        rule_quality: str,
    ) -> bool:
        """判断是否需要调用 LLM 补充建议。

        调用 LLM 当：LLM 可用 且 (规则结果是 generic 即未针对具体失效模式，
        或 既无高置信建议且数量不足)。
        rule_quality 是"是否针对当前失效模式"的真实信号——measure/optimization
        的规则结果常以 AP 分级给出通用模板(confidence 0.6 但质量 generic)，不应
        因此阻止 LLM 给出针对性建议。
        """
        return llm_available and (
            rule_quality == "generic" or (not has_specific and suggestion_count < 3)
        )

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

    async def _get_cached(
        self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str, effective_scope: str
    ) -> tuple[RecommendResponse, bool] | None:
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
            suggestions = row.suggestions
            graph_count = sum(1 for s in suggestions if s.get("source") == "graph")
            response = RecommendResponse(
                suggestions=suggestions,
                source=row.source,
                cached=True,
                llm_available=self.llm is not None,
                graph_match_count=graph_count,
                effective_scope=effective_scope,
            )
            return (response, row.llm_available)
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
                expires_at=func.now() + text("INTERVAL '24 hours'"),
                suggestions=[s.model_dump() for s in response.suggestions],
                source=response.source,
                llm_available=self.llm is not None,
            )
            .on_conflict_do_update(
                index_elements=["fmea_id", "trigger_type", "context_hash"],
                index_where=text("fmea_id IS NOT NULL"),
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

        class _SafeDict(dict):
            """format_map helper: missing keys render as empty string instead
            of raising KeyError (which would silently send an unfilled prompt)."""

            def __missing__(self, key):
                return ""

        safe = _SafeDict()
        safe.update({k: v for k, v in context.get("current_context", {}).items()})
        safe.update({k: v for k, v in context.items() if k != "current_context"})
        safe["historical_patterns"] = json.dumps(context.get("historical_patterns", []), ensure_ascii=False)
        return template.format_map(safe)
