import hashlib
import json
import logging
import uuid

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.recommendation_cache import RecommendationCache
from app.models.user import User
from app.schemas.recommendation_stage import StageRunSchema
from app.services.agent import audit as audit_mod
from app.services.recommendation_orchestrator import RecommendationOrchestrator
from app.services.recommendation_types import (
    RecommendationCandidate,
    RecommendationContext,
    RecommendationResult,
    StageRun,
)

logger = logging.getLogger(__name__)


class HybridRecommendationPipeline:
    """8D D4/D5 全混合推荐管道（薄壳）：委托 RecommendationOrchestrator 执行 12 阶段流水线。"""

    def __init__(self, db, pc, embedding_provider, llm_timeout: float | None = None):
        self.db = db
        self.pc = pc
        self.embedding = embedding_provider
        self.orchestrator = RecommendationOrchestrator(
            db, pc, embedding_provider, llm_timeout=llm_timeout
        )

    async def recommend(
        self,
        context: RecommendationContext,
        *,
        user: User,
        report_id: uuid.UUID,
        factory_id: uuid.UUID,
        tenant_schema: str,
    ) -> RecommendationResult:
        """执行完整推荐管道。"""
        result = await self.orchestrator.run(
            context,
            user=user,
            report_id=report_id,
            factory_id=factory_id,
            tenant_schema=tenant_schema,
        )
        if not result.blocked:  # BLOCKED 时跳过审计与 cache 写入
            await self._maybe_write_llm_audit(
                result, context, user, report_id, factory_id, tenant_schema
            )
            await self._cache_capa_result(report_id, context, result)
        return result

    def _serialize_capa_suggestions(self, stage: str, items: list[RecommendationCandidate]) -> list[dict]:
        """统一为候选 list + kind 判别（D4: d4_cause；D5: d5_control|d5_suggestion 互斥单次遍历）。"""
        out: list[dict] = []
        if stage == "d4":
            for c in items:
                out.append({"kind": "d4_cause", **c.to_d4_schema()})
        else:  # d5
            for c in items:
                control = c.to_d5_control_schema()
                if control:
                    out.append({"kind": "d5_control", **control})
                else:
                    out.append({"kind": "d5_suggestion", **c.to_d5_suggestion_schema()})
        return out

    async def _cache_capa_result(self, report_id, context: RecommendationContext, result: RecommendationResult) -> None:
        """CAPA 专属缓存写入（write-only，report_id 键 + uq_cache_capa upsert）。"""
        if report_id is None:
            return
        context_hash = hashlib.sha256(json.dumps({
            "d2": context.capa_data.get("d2_description"),
            "d3": context.capa_data.get("d3_interim"),
            "d4": context.capa_data.get("d4_root_cause"),
            "fmea_ref_id": str(context.capa_data.get("fmea_ref_id")) if context.capa_data.get("fmea_ref_id") else None,
            "fmea_node_id": context.capa_data.get("fmea_node_id"),
            "product_line_code": context.capa_data.get("product_line_code"),
        }, sort_keys=True, default=str).encode()).hexdigest()[:16]
        trigger_type = context.stage
        suggestions = self._serialize_capa_suggestions(context.stage, result.items)
        try:
            # 整个列表推导放入 try（StageRunSchema 构造 + model_dump 才是可能抛错点）
            stage_runs_json = [StageRunSchema(**s.__dict__).model_dump() for s in result.stages]
        except Exception as e:
            logger.warning(f"stage_runs serialize failed (degrade to NULL): {e}")
            stage_runs_json = None
        source = "hybrid"
        stmt = (
            pg_insert(RecommendationCache)
            .values(
                report_id=report_id, trigger_type=trigger_type, context_hash=context_hash,
                product_line_code=context.capa_data.get("product_line_code") or "",
                factory_id=context.factory_id, doc_type="capa",
                suggestions=suggestions, stage_runs=stage_runs_json, source=source,
                llm_available=(self.pc is not None),
                expires_at=func.now() + text("INTERVAL '24 hours'"),
            )
            .on_conflict_do_update(
                index_elements=["report_id", "trigger_type", "context_hash"],
                index_where=text("report_id IS NOT NULL"),
                set_={
                    "suggestions": suggestions, "stage_runs": stage_runs_json, "source": source,
                    "llm_available": (self.pc is not None), "created_at": func.now(),
                    "expires_at": func.now() + text("INTERVAL '24 hours'"),
                },
            )
        )
        await self.db.execute(stmt)

    async def _maybe_write_llm_audit(
        self,
        result: RecommendationResult,
        context: RecommendationContext,
        user: User,
        report_id: uuid.UUID,
        factory_id: uuid.UUID,
        tenant_schema: str,
    ) -> None:
        # R4-修复：从 stage 11 StageRun 结构化字段取计数（非 summary 字符串），避免 error 时审计层抛错
        stage11 = next((s for s in result.stages if s.index == 11), None)
        if stage11 is None or stage11.llm_attempted is None or stage11.llm_attempted == 0:
            return  # skipped（无 pc）/ error（attempted=0）→ 无 LLM 尝试，不写 llm_recommend audit

        if stage11.llm_failed == 0:
            status = "success"
        elif stage11.llm_failed < stage11.llm_attempted:
            status = "partial"
        else:
            status = "llm_failed"

        capa_hash = hashlib.sha256(
            json.dumps(context.capa_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        correlation_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{context.stage}_recommend:{report_id}:{capa_hash}",
        )

        try:
            await audit_mod.write_audit_raw(
                self.db,
                user_id=user.user_id,
                factory_id=factory_id,
                tenant_schema=tenant_schema,
                table_name="capa_eightd",
                record_id=report_id,
                action="llm_recommend",
                correlation_id=correlation_id,
                new_values={
                    "status": status,
                    "trigger": context.stage,
                    "attempted": stage11.llm_attempted,
                    "succeeded": stage11.llm_succeeded,
                    "failed": stage11.llm_failed,
                },
            )
        except Exception as e:
            logger.warning(f"llm_recommend audit write failed (non-blocking): {e}")
