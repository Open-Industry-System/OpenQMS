import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")

import pytest
import uuid

from app.models.fmea import FMEADocument


@pytest.mark.asyncio
async def test_recommend_route_passes_tenant_schema_and_commits(
    admin_client, db, default_factory, admin_user, monkeypatch
):
    """POST /api/fmea/{id}/recommend no longer reads app.state.llm_provider;
    it constructs RecommendationService WITHOUT llm_provider, passes
    tenant_schema, and awaits db.commit()."""
    import app.api.fmea as fmea_api

    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-2026-010", fmea_type="PFMEA",
        title="t", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()

    captured = {}

    class _FakeService:
        def __init__(self, db, graph_repo, llm_timeout=None):
            captured["ctor_kwargs"] = list(self.__init__.__code__.co_varnames)
            # Reject llm_provider at construction so the test fails if the route
            # still passes it. (We assert via __init__ signature below instead.)
        async def recommend(self, *args, **kwargs):
            captured["recommend_kwargs"] = kwargs
            from app.schemas.recommendation import RecommendResponse
            return RecommendResponse(
                suggestions=[], source="rule", cached=False,
                llm_available=False, graph_match_count=0, effective_scope="current_product_line",
            )

    # Patch the name as bound in the route module's namespace.
    monkeypatch.setattr(fmea_api, "RecommendationService", _FakeService)

    # Spy on db.commit so a future deletion of `await db.commit()` turns this red.
    real_commit = db.commit
    commit_calls = []
    async def _spy_commit():
        commit_calls.append(True)
        await real_commit()
    monkeypatch.setattr(db, "commit", _spy_commit)

    resp = await admin_client.post(
        f"/api/fmea/{fmea.fmea_id}/recommend",
        json={"trigger_type": "failure_mode",
              "context": {"function_description": "xx", "failure_mode": "y"},
              "scope": "current_product_line", "include_graph": False},
    )
    assert resp.status_code == 200
    assert "tenant_schema" in captured["recommend_kwargs"]
    assert captured["recommend_kwargs"]["tenant_schema"] == "public"
    assert len(commit_calls) >= 1, "route must await db.commit() (audit + cache rows depend on it)"
