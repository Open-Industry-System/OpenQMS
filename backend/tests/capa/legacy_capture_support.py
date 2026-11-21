"""New pure-rule candidate fixtures for legacy append/retry transaction tests.

These tests model a generated rule with genuinely empty external S. They do
not attach current FMEA/CAPA references to old unbound history. Full protected
source acceptance uses test_r6_legacy_capture and the real orchestrator.
"""
from uuid import UUID
from app.services.capa_legacy_capture import store
from app.services.capa_d4_material import material_version
from app.services.recommendation_types import RecommendationCandidate


async def bind_rule_candidate(db,capa,request,actor):
    if request.capture_id is None:
        assert request.source in {'rule','manual'}, 'use a real protected-source capture fixture instead'
        assert not any(key in (request.item_ref or {}) for key in ('fmea_id','historical_capa_id','source_capa_id','capa_id'))
        item=RecommendationCandidate(source='rule',content=request.adopted_text,category=None,
            confidence=1,match_reason='generated pure-rule test fixture',metadata=dict(request.item_ref or {},stage_index=request.stage_index))
        await store(db,report_id=capa.report_id,actor=actor,stage=request.d_step,items=[item],sources=[],
            target_material=await material_version(db,capa.report_id))
        await db.commit()
        request.capture_id=UUID(item.metadata['capture_id'])
    return request


async def adopt_rule_candidate(db,capa,request,actor):
    from app.services.capa_verification_service import adopt_recommendation
    await bind_rule_candidate(db,capa,request,actor)
    return await adopt_recommendation(db,capa,request,actor)
