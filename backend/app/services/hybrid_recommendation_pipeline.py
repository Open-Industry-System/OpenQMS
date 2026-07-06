import hashlib
import json
import logging
import uuid

from app.models.user import User
from app.services.agent import audit as audit_mod
from app.services.recommendation_orchestrator import RecommendationOrchestrator
from app.services.recommendation_types import (
    RecommendationContext,
    RecommendationResult,
)

logger = logging.getLogger(__name__)


class HybridRecommendationPipeline:
    """8D D4/D5 全混合推荐管道（薄壳）：委托 RecommendationOrchestrator 执行 12 阶段流水线。"""

    def __init__(self, db, pc, embedding_provider):
        self.db = db
        self.pc = pc
        self.embedding = embedding_provider
        self.orchestrator = RecommendationOrchestrator(db, pc, embedding_provider)

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
        await self._maybe_write_llm_audit(
            result, context, user, report_id, factory_id, tenant_schema
        )
        return result

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
