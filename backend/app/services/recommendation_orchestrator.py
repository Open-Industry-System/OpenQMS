"""RecommendationOrchestrator: 12-stage recall → fusion → LLM → terminal pipeline.

Implements the DAG-provenance design (Spec B): 12 named stages with unique
indexes, fusion-before-LLM ordering, LLM failure isolation, no-data vs done(0)
distinction, D5 derived-stage boundary, and per-stage source-protocol checks.

Task 3 registers ONLY the 6 existing sources (new sources arrive in Tasks 5-10).
`_lookup_linked_fmea_causes` is a stub returning [] (completed in Task 11).
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Literal

from app.services.fusion_engine import FusionEngine
from app.services.llm_fusion_layer import LLMFusionLayer
from app.services.recommendation_sources import (
    FMEAControlExpander,
    FMEAGraphSource,
    HistoricalCAPAMeasureSource,
    HistoricalCAPASource,
    RuleEngineMeasureSource,
    RuleEngineSource,
    SemanticSearchSource,
)
from app.services.recommendation_sources_extra import (
    IQCSource,
    LessonsLearnedSource,
    MESSource,
    SameTypeProductKBSource,
    SPCAnomalySource,
    SupplierHistorySource,
)
from app.services.recommendation_types import (
    RecommendationCandidate,
    RecommendationContext,
    RecommendationResult,
    StageRun,
)

logger = logging.getLogger(__name__)


@dataclass
class StageSpec:
    index: int
    name: str
    source_kind: str            # 'fmea_graph' | 'semantic_search' | ... | 'internal' | 'llm'
    stage_filter: Literal["d4", "d5", "both"]
    skipped_reason: str | None = None   # 静态 skipped（如 D5 不适用）
    derived: bool = False               # 派生阶段：消费已召回候选，非独立 retrieve（决策 15，D5 stage 2）
    terminal: bool = False              # 终态阶段：主循环跳过，fusion 后单次发射（决策 16，stage 12）
    d5_source_kind: str | None = None   # D5 覆盖 source：D4 用 source_kind，D5 用本字段（如 stage 10 措施规则）
    extra_sources_d4: list[str] = field(default_factory=list)
    extra_sources_d5: list[str] = field(default_factory=list)


STAGE_PLAN: list[StageSpec] = [
    StageSpec(1,  "上下文采集",        "internal",        "both"),
    StageSpec(2,  "本产品 FMEA 检索",   "fmea_graph",      "both"),   # D5: derived（下方 executes_after）
    StageSpec(3,  "全局知识库 RAG 检索", "semantic_search", "both", extra_sources_d4=["historical_capa"]),
    StageSpec(4,  "同类型产品 KB 检索",  "same_type_product_kb", "both"),
    StageSpec(5,  "经验教训库检索",     "lessons_learned", "both", extra_sources_d5=["historical_capa_measure"]),
    StageSpec(6,  "SPC 异常关联检索",   "spc_anomaly",     "d4"),
    StageSpec(7,  "MES 设备/过程检索",  "mes",             "d4"),
    StageSpec(8,  "IQC 来料检索",       "iqc",             "d4"),
    StageSpec(9,  "供货历史检索",       "supplier_history","d4"),
    StageSpec(10, "规则启发",           "rule_engine",     "both", d5_source_kind="rule_engine_measure"),
    StageSpec(11, "LLM 融合排序",       "llm",             "both"),
    StageSpec(12, "输出推荐列表",       "internal",        "both", terminal=True),
]
# D5 stage 2 标派生（决策 15）：FMEAControlExpander 消费 stage 3/4 召回的 cause
_D5_DERIVED = {2: "FMEAControlExpander"}   # index -> 派生处理器


class RecommendationOrchestrator:
    def __init__(self, db, pc, embedding_provider):
        self.db = db; self.pc = pc; self.embedding = embedding_provider
        self.fusion = FusionEngine(); self.llm_layer = LLMFusionLayer(pc)
        self.d5_control_expander = FMEAControlExpander()   # D5 stage 2 派生处理器（决策 15）
        self._sources = self._build_sources()   # source_kind -> instance（D5 stage 2 不在此列，派生）
        # R10-修复：不在构造时 fail-fast 校验协议——避免单源配置错误导致所有 D4/D5 请求硬失败（含 D4-only 源本应 skipped 的 D5 请求）。
        # 协议校验改为 per-stage 运行时（_exec_recall_stage 内，违规 → 该 stage error，其余 stage + 12 阶段响应照常）。
        # 启动/CI 应另跑 `validate_all_new_sources()` lint（见下）提前发现配置错误。

    NEW_SOURCE_KINDS = frozenset({"spc_anomaly", "iqc", "supplier_history", "mes", "same_type_product_kb", "lessons_learned"})

    def _build_sources(self):
        # Task 3: only the 6 existing sources. New sources (same_type_product_kb,
        # lessons_learned, spc_anomaly, mes, iqc, supplier_history) arrive in Tasks 5-10.
        # FMEAGraphSource / RuleEngineSource / RuleEngineMeasureSource have no __init__
        # (they read from context / construct RuleEngine inline); the db-backed sources
        # take (db, embedding_provider).
        return {
            "fmea_graph": FMEAGraphSource(),
            "semantic_search": SemanticSearchSource(self.db, self.embedding),
            # historical_capa: D4 stage 3 extra (global KB RAG recalls similar past CAPA root causes);
            # historical_capa_measure: D5 stage 5 extra (lessons learned + historical correction measures).
            "historical_capa": HistoricalCAPASource(self.db, self.embedding),
            "historical_capa_measure": HistoricalCAPAMeasureSource(self.db, self.embedding),
            "rule_engine": RuleEngineSource(),
            "rule_engine_measure": RuleEngineMeasureSource(),
            "spc_anomaly": SPCAnomalySource(self.db, self.embedding),
            "mes": MESSource(self.db, self.embedding),
            "iqc": IQCSource(self.db, self.embedding),
            "supplier_history": SupplierHistorySource(self.db, self.embedding),
            "same_type_product_kb": SameTypeProductKBSource(self.db, self.embedding),
            "lessons_learned": LessonsLearnedSource(self.db, self.embedding),
        }

    def _check_source_protocol(self, spec, source, kind=None) -> str | None:
        # R10-修复：per-stage 运行时协议校验（不阻断构造/整请求）。新源 should_skip 必须存在、可调用、async。
        # 违规 → 返回 error reason（该 stage 标 error，其余 stage + 12 阶段响应照常）；合规 → None
        # kind 为实际执行的 source_kind（D5 可能被 d5_source_kind 覆盖）。
        kind = kind or spec.source_kind
        if kind not in self.NEW_SOURCE_KINDS:
            return None   # 既有源无 should_skip 协议要求
        if source is None:
            return f"source {kind} 未注册"
        if not callable(getattr(source, "should_skip", None)):
            return f"source {kind} should_skip 不可调用"
        if not inspect.iscoroutinefunction(source.should_skip):
            return f"source {kind} should_skip 非 async"
        return None

    def validate_all_new_sources(self) -> list[str]:
        # R10-修复：启动/CI lint（非请求路径），返回违规列表供提前发现配置错误；不 raise
        violations = []
        for spec in STAGE_PLAN:
            if spec.source_kind in self.NEW_SOURCE_KINDS:
                v = self._check_source_protocol(spec, self._sources.get(spec.source_kind))
                if v: violations.append(f"stage {spec.index} {spec.name}: {v}")
        return violations

    async def run(self, context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult:
        # 顶部 BLOCKED 判定（AI_REQUIRED=true，故事契约不可降级）
        if self.pc is None:
            return RecommendationResult(items=[], stages=self._blocked_stages(), blocked=True)

        stages: list[StageRun] = []
        all_candidates: list[RecommendationCandidate] = []

        # ── 召回遍：stage 1-10（跳过 11 LLM、12 terminal、D5 stage 2 derived）──
        # 顺序合约（R2-修复 LLM/融合顺序）：recall → fusion → LLM，与既有管线一致——LLM 吃 fused 集，不吃 raw
        for spec in STAGE_PLAN:
            if spec.terminal or spec.source_kind == "llm":
                continue   # stage 12 terminal 留末尾；stage 11 LLM 留 fusion 之后
            if context.stage == "d5" and spec.index in _D5_DERIVED:
                continue   # D5 stage 2 派生留派生遍
            stages.append(await self._exec_recall_stage(spec, context, all_candidates))

        # ── 派生遍：D5 stage 2 FMEAControlExpander over stage 3/4 召回 causes + linked FMEA 直查 causes（决策 15 + R3 边界 + R4 guard + R10-修复）──
        if context.stage == "d5":
            spec = next(s for s in STAGE_PLAN if s.index == 2)
            semantic_causes = [c for c in all_candidates
                               if c.metadata.get("failure_cause_node_id") and c.metadata.get("stage_index") in (3, 4)]   # R3-修复：仅 stage 3/4 召回的 cause
            # R10-修复：D5 stage 2 不只依赖 semantic（embedding 不可用 / semantic 0 命中时仍能扩展 FMEA 控制措施）——
            # 直接从 linked FMEA 按 D4 根因关键词查 FailureCause（与既有纯函数 _match_existing_controls 一致，不依赖 embedding）
            direct_causes = await self._lookup_linked_fmea_causes(context)
            # 合并 + 按 (fmea_id, failure_cause_node_id) 去重
            seen: set = set(); cause_cands = []
            for c in semantic_causes + direct_causes:
                k = (c.metadata.get("fmea_id"), c.metadata.get("failure_cause_node_id"))
                if k not in seen:
                    seen.add(k); cause_cands.append(c)
            if not cause_cands:
                # R4-修复：无 FMEA cause（semantic + linked FMEA 直查均空）→ skipped，不调 expand 误报 done(0)
                stages.append(StageRun(2, spec.name, "fmea_graph", "skipped",
                                       summary="D5 无 FMEA cause（semantic + linked FMEA 直查均空），跳过控制扩展"))
            else:
                try:
                    controls = await self.d5_control_expander.expand(cause_cands, context.fmea_docs or [])
                    for c in controls:
                        c.metadata["stage_index"] = 2
                    all_candidates.extend(controls)
                    stages.append(StageRun(2, spec.name, "fmea_graph", "done",
                                           hit_count=len(controls), summary=f"扩展 {len(controls)} 条 FMEA 控制措施"))
                except Exception as e:
                    logger.warning(f"D5 stage 2 FMEAControlExpander failed: {e}")
                    stages.append(StageRun(2, spec.name, "fmea_graph", "error", error=str(e)[:200]))

        # ── Fusion（既有序：fusion 在 LLM 之前，R2-修复顺序）──
        fused = self.fusion.merge(all_candidates, context)

        # ── Stage 11 LLM enrich over FUSED（不是 raw，保既有合约，R2-修复）──
        spec11 = next(s for s in STAGE_PLAN if s.index == 11)
        stage11, enriched = await self._exec_llm_stage(spec11, fused, context)
        stages.append(stage11)
        fused = enriched   # LLM 增强后的 fused 集

        # ── Stage 12 terminal 单次发射（决策 16）──
        stages.append(StageRun(12, "输出推荐列表", "internal", "done",
                               hit_count=len(fused), summary=f"输出 {len(fused)} 条带来源推荐"))

        # 按 index 排序，保证显示顺序 1..12
        stages.sort(key=lambda s: s.index)
        return RecommendationResult(items=fused, stages=stages)

    def _blocked_stages(self) -> list[StageRun]:
        """pc=None 时构造 12 行结构化 BLOCKED 状态（stage 1 done、stage 11 blocked、其余 skipped）。"""
        stages: list[StageRun] = []
        for spec in STAGE_PLAN:
            if spec.index == 1:
                stages.append(StageRun(spec.index, spec.name, "internal", "done",
                                       summary="上下文已采集（D2/D4 + 关联 FMEA + 产品线）"))
            elif spec.index == 11:
                stages.append(StageRun(spec.index, spec.name, "llm", "blocked",
                                       summary="未配置 LLM 凭证"))
            else:
                stages.append(StageRun(spec.index, spec.name, spec.source_kind, "skipped",
                                       summary="LLM 未配置，编排未执行"))
        stages.sort(key=lambda s: s.index)
        return stages

    async def _exec_recall_stage(self, spec, context, all_candidates) -> StageRun:
        # 解析本 stage 在当前上下文要执行的 source 列表：primary（DAG 标签）+ extras
        primary = spec.d5_source_kind if (context.stage == "d5" and spec.d5_source_kind) else spec.source_kind
        extras = spec.extra_sources_d4 if context.stage == "d4" else spec.extra_sources_d5
        kinds = [primary] + list(extras)

        # 1. stage_filter 不匹配 → skipped
        if spec.stage_filter != "both" and spec.stage_filter != context.stage:
            return StageRun(spec.index, spec.name, primary, "skipped",
                            summary=f"{context.stage.upper()} 阶段不适用")
        # 2. internal（stage 1 上下文）
        if primary == "internal":
            return StageRun(spec.index, spec.name, "internal", "done",
                            summary="上下文已采集（D2/D4 + 关联 FMEA + 产品线）")

        # 3. 结构性前置：组合阶段中任一源依赖 embedding/linked_fmea 则整阶段 skipped
        pre = self._stage_precondition(spec, context, kinds)
        if pre:
            return StageRun(spec.index, spec.name, primary, "skipped", summary=pre)

        stage_candidates: list[RecommendationCandidate] = []
        per_source_summary: list[str] = []
        primary_errors: list[str] = []
        extra_errors: list[str] = []
        skipped_sources: list[str] = []

        for kind in kinds:
            source = self._sources.get(kind)
            if source is None:
                if kind == primary:
                    primary_errors.append(f"source {kind} 未注册")
                else:
                    logger.warning(f"Stage {spec.index} extra source {kind} not registered, skipping")
                continue

            # 协议校验仅对新源；额外源违规时跳过，不阻断主源
            if kind in self.NEW_SOURCE_KINDS:
                proto_violation = self._check_source_protocol(spec, source, kind)
                if proto_violation:
                    if kind == primary:
                        primary_errors.append(proto_violation)
                    else:
                        logger.warning(f"Stage {spec.index} extra source {kind} protocol violation, skipping: {proto_violation}")
                    continue

            try:
                # should_skip：按源独立处理。主源 skipped 且无候选时 stage skipped；额外源 skipped 仅跳过自身
                if hasattr(source, "should_skip"):
                    skip_reason = await source.should_skip(context)
                    if skip_reason:
                        if kind == primary:
                            skipped_sources.append(f"{kind}: {skip_reason}")
                        else:
                            logger.warning(f"Stage {spec.index} extra source {kind} skipped: {skip_reason}")
                        continue

                candidates = await source.retrieve(context)
                for c in candidates:
                    c.metadata["stage_index"] = spec.index
                stage_candidates.extend(candidates)
                if candidates:
                    per_source_summary.append(f"{kind}: {len(candidates)}")
            except Exception as e:
                logger.warning(f"Stage {spec.index} {spec.name} source {kind} failed: {e}")
                if kind == primary:
                    primary_errors.append(f"{kind}: {str(e)[:100]}")
                else:
                    extra_errors.append(f"{kind}: {str(e)[:100]}")

        all_candidates.extend(stage_candidates)

        # 4. 组合结果汇总：source 标签保持 primary，hit_count 为所有源候选总数
        # 主源失败 → stage error（保留既有行为）
        if primary_errors:
            errors = primary_errors + extra_errors
            return StageRun(spec.index, spec.name, primary, "error",
                            error="; ".join(errors),
                            summary=f"组合执行失败: {'; '.join(errors)}")

        # 主源被静态 skipped → 保持 skipped，不因额外源失败而转 error
        if skipped_sources:
            return StageRun(spec.index, spec.name, primary, "skipped",
                            summary="; ".join(skipped_sources))

        # 主源成功但额外源失败 → 失败必须可观测；若无候选则整体 error（避免 done(0) 隐藏失败）
        if extra_errors:
            error_str = "; ".join(extra_errors)
            if stage_candidates:
                summary = ", ".join(per_source_summary) if per_source_summary else f"{primary}: {len(stage_candidates)}"
                summary += f" | extra failures: {error_str}"
                return StageRun(spec.index, spec.name, primary, "done",
                                hit_count=len(stage_candidates), error=error_str, summary=summary)
            return StageRun(spec.index, spec.name, primary, "error",
                            error=error_str,
                            summary=f"stage produced no candidates; extra failures: {error_str}")

        if stage_candidates:
            summary = ", ".join(per_source_summary) if per_source_summary else f"{primary}: {len(stage_candidates)}"
            return StageRun(spec.index, spec.name, primary, "done",
                            hit_count=len(stage_candidates), summary=summary)

        return StageRun(spec.index, spec.name, primary, "done",
                        hit_count=0, summary=f"{primary}: 0")

    def _stage_precondition(self, spec, context, kinds) -> str | None:
        # R3-修复：集中既有源 + 新源共用的结构性前置条件（不要求既有源新增 should_skip）
        # 组合执行：检查 kinds 列表中任一源是否依赖缺失的 embedding / linked_fmea
        if "fmea_graph" in kinds and context.stage == "d4" and not context.linked_fmea:
            return "未关联 FMEA"
        embedding_dependent = {"semantic_search", "same_type_product_kb", "lessons_learned",
                               "historical_capa", "historical_capa_measure"}
        if self.embedding is None and any(k in embedding_dependent for k in kinds):
            return "未配置 embedding"
        return None

    async def _lookup_linked_fmea_causes(self, context) -> list[RecommendationCandidate]:
        # R10-修复：D5 stage 2 直查 linked FMEA 的 FailureCause（按 D4 根因关键词），不依赖 embedding。
        # embedding 不可用 / semantic 0 命中时仍能扩展 FMEA 控制措施（与既有纯函数 _match_existing_controls 一致）。
        from app.utils.text import extract_keywords
        linked = context.linked_fmea
        if not linked or not linked.get("graph_data"):
            return []
        d4 = context.capa_data.get("d4_root_cause", "") or context.capa_data.get("d2_description", "")
        keywords = extract_keywords(d4)
        if not keywords:
            return []
        graph = linked["graph_data"]; node_map = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])
        forward: dict[str, list] = {}
        for e in edges:
            forward.setdefault(e["source"], []).append((e["target"], e["type"]))
        cands: list[RecommendationCandidate] = []
        for node in graph.get("nodes", []):
            if node.get("type") != "FailureCause":
                continue
            name = node.get("name", ""); desc = node.get("description", "")
            if not any(kw in name or kw in desc for kw in keywords):
                continue
            fm_id = fm_name = None
            for tgt, etype in forward.get(node["id"], []):
                if etype == "CAUSE_OF" and node_map.get(tgt, {}).get("type") == "FailureMode":
                    fm_id = tgt; fm_name = node_map[tgt].get("name"); break
            cands.append(RecommendationCandidate(
                source="fmea_graph", content=name, category=None, confidence=0.5,
                match_reason="关联 FMEA 失效原因（D4 关键词直查）",
                metadata={"failure_cause_node_id": node["id"], "failure_cause_desc": desc or None,
                          "failure_mode_node_id": fm_id, "failure_mode_name": fm_name,
                          "fmea_id": str(linked["fmea_id"]), "fmea_document_no": linked.get("document_no"),
                          "product_line_code": linked.get("product_line_code"), "stage_index": 2}))
        return cands

    async def _exec_llm_stage(self, spec, fused, context) -> tuple[StageRun, list[RecommendationCandidate]]:
        # LLM enrich over FUSED 集（保既有 fusion→LLM 顺序，R2-修复）；返回 (StageRun, 增强后候选)
        if self.pc is None:
            return StageRun(spec.index, spec.name, "llm", "skipped", summary="未配置 LLM",
                            llm_attempted=0, llm_succeeded=0, llm_failed=0), fused
        try:
            outcome = await self.llm_layer.enrich(fused, context)
            for c in outcome.candidates:
                c.metadata.setdefault("stage_index", spec.index)
            # R6+R11-修复：全失败（attempted>0 且 succeeded=0）→ status='error'（不绿，DAG 显红），
            # **返回原 fused 候选（非 outcome.candidates——后者可能为空，会丢确定性 fused 推荐，R11-修复）**
            # + 写 llm_failed audit（attempted>0）；部分失败 → done（summary 记 failed 计数），返回 outcome.candidates
            status = "error" if (outcome.attempted > 0 and outcome.succeeded == 0) else "done"
            returned_cands = fused if status == "error" else outcome.candidates
            if status == "done":
                for c in returned_cands:
                    c.metadata.setdefault("stage_index", spec.index)
            return StageRun(spec.index, spec.name, "llm", status,
                            hit_count=len(returned_cands),
                            summary=f"attempted={outcome.attempted} succeeded={outcome.succeeded} failed={outcome.failed}",
                            llm_attempted=outcome.attempted, llm_succeeded=outcome.succeeded, llm_failed=outcome.failed), returned_cands
        except Exception as e:
            # R3+R4+R5-修复：LLMFusionLayer.enrich 已硬化为 catch-all（见下），正常不会抛——此 except 仅兜底
            # 意外的非 LLM 调用错误（如 prompt 构造 bug），此时无 provider 调用完成，attempted=0 诚实，不审计。
            # enrich 内部全失败（provider 调用 attempted>0 全 failed）→ 不抛，返回 LLMOutcome(attempted>0, succeeded=0, failed=attempted)
            # → stage 11 error（R6-修复：全失败显 error 不绿）+ llm_attempted>0 → _maybe_write_llm_audit 写 status="llm_failed"（全失败也审计，R5-修复）
            logger.warning(f"Stage 11 LLM enrich unexpected error: {e}")
            for c in fused:
                c.metadata.setdefault("stage_index", spec.index)
            return StageRun(spec.index, spec.name, "llm", "error", error=str(e)[:200],
                            summary="LLM 增强失败，保留 fused 候选",
                            llm_attempted=0, llm_succeeded=0, llm_failed=0), fused
