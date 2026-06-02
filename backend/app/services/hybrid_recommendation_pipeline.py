import logging

from app.services.fusion_engine import FusionEngine
from app.services.llm_fusion_layer import LLMFusionLayer
from app.services.recommendation_sources import (
    FMEAGraphSource,
    SemanticSearchSource,
    HistoricalCAPASource,
    HistoricalCAPAMeasureSource,
    RuleEngineSource,
    RuleEngineMeasureSource,
    FMEAControlExpander,
)
from app.services.recommendation_types import (
    RecommendationContext,
    RecommendationResult,
)

logger = logging.getLogger(__name__)


class HybridRecommendationPipeline:
    """8D D4/D5 全混合推荐管道。"""

    def __init__(self, db, llm_provider, embedding_provider):
        self.db = db
        self.llm = llm_provider
        self.embedding = embedding_provider

        # D4 Sources
        self.d4_sources = [
            FMEAGraphSource(),
            SemanticSearchSource(db, embedding_provider),
            HistoricalCAPASource(db, embedding_provider),
            RuleEngineSource(),
        ]

        # D5 Sources (Stage 1: text/semantic recall)
        self.d5_sources = [
            SemanticSearchSource(db, embedding_provider),
            HistoricalCAPAMeasureSource(db, embedding_provider),
            RuleEngineMeasureSource(),
        ]

        # D5 Stage 2: control expander (not an independent Source)
        self.d5_control_expander = FMEAControlExpander()

        self.fusion = FusionEngine()
        self.llm_layer = LLMFusionLayer(llm_provider)

    async def recommend(self, context: RecommendationContext) -> RecommendationResult:
        """执行完整推荐管道。"""
        stage = context.stage
        all_candidates = []

        # --- Stage 1: 召回 ---
        sources = self.d4_sources if stage == "d4" else self.d5_sources

        for source in sources:
            try:
                candidates = await source.retrieve(context)
                all_candidates.extend(candidates)
                logger.debug(f"Source {source.name} returned {len(candidates)} candidates")
            except Exception as e:
                logger.warning(f"Source {source.name} failed: {e}")

        # --- D5 Stage 2: Control expansion ---
        if stage == "d5":
            # Collect FailureCause candidates from Stage 1 for expander
            cause_candidates = [
                c for c in all_candidates
                if c.metadata.get("failure_cause_node_id")
            ]
            if cause_candidates and context.fmea_docs is not None:
                try:
                    control_candidates = await self.d5_control_expander.expand(
                        cause_candidates, context.fmea_docs
                    )
                    all_candidates.extend(control_candidates)
                except Exception as e:
                    logger.warning(f"FMEAControlExpander failed: {e}")

        # --- Stage 3: 融合去重排序 ---
        fused = self.fusion.merge(all_candidates, context)

        # --- Stage 4: LLM 增强 ---
        enriched = await self.llm_layer.enrich(fused, context)

        return RecommendationResult(items=enriched)
