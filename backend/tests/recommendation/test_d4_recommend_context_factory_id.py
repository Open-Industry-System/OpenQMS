import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.main import app
from app.models.capa import CAPAEightD


def _fake_recommend(captured: dict):
    async def fake_recommend(self, context, **kw):
        captured["factory_id"] = context.factory_id
        from app.services.recommendation_types import RecommendationResult

        return RecommendationResult(items=[], stages=[])

    return fake_recommend


@pytest.mark.asyncio
async def test_d4_handler_passes_factory_id_in_context(
    admin_client, db, default_factory, admin_user, monkeypatch
):
    """D4 handler 构造的 RecommendationContext 必须携带 capa.factory_id。"""
    captured = {}
    monkeypatch.setattr(
        "app.services.hybrid_recommendation_pipeline.HybridRecommendationPipeline.recommend",
        _fake_recommend(captured),
    )

    from app.services.agent import provider_adapter

    monkeypatch.setattr(provider_adapter, "build_client", AsyncMock(return_value=MagicMock()))
    app.state.embedding_provider = None

    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no="8D-2026-D4-FID",
        title="D4 factory_id passthrough",
        factory_id=default_factory.id,
        product_line_code="DC-DC-100",
        status="D2_DESCRIPTION",
    )
    db.add(capa)
    await db.commit()

    r = await admin_client.get(f"/api/capa/{capa.report_id}/d4-fmea-recommendations")
    assert r.status_code == 200, r.text
    assert captured["factory_id"] == capa.factory_id


@pytest.mark.asyncio
async def test_d5_handler_passes_factory_id_in_context(
    admin_client, db, default_factory, admin_user, monkeypatch
):
    """D5 handler 构造的 RecommendationContext 必须携带 capa.factory_id。"""
    captured = {}
    monkeypatch.setattr(
        "app.services.hybrid_recommendation_pipeline.HybridRecommendationPipeline.recommend",
        _fake_recommend(captured),
    )

    from app.services.agent import provider_adapter

    monkeypatch.setattr(provider_adapter, "build_client", AsyncMock(return_value=MagicMock()))
    app.state.embedding_provider = None

    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no="8D-2026-D5-FID",
        title="D5 factory_id passthrough",
        factory_id=default_factory.id,
        product_line_code="DC-DC-100",
        status="D4_ROOT_CAUSE",
    )
    db.add(capa)
    await db.commit()

    r = await admin_client.get(f"/api/capa/{capa.report_id}/d5-fmea-recommendations")
    assert r.status_code == 200, r.text
    assert captured["factory_id"] == capa.factory_id
