import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
import uuid
import pytest
from app.models.fmea import FMEADocument


@pytest.mark.asyncio
async def test_recommend_reports_three_required_retrievers(
    admin_client, db, default_factory, admin_user
):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-OBS-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    resp = await admin_client.post(
        f"/api/fmea/{fmea.fmea_id}/recommend",
        json={"trigger_type": "failure_mode",
              "context": {"function_description": "焊接"},
              "include_graph": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    sources = {e["source"] for e in body["source_executions"]}
    assert {"graph", "semantic_search", "lessons_learned"} <= sources
    for e in body["source_executions"]:
        assert e["status"] in ("success", "empty", "unavailable", "error")
    assert body["context_execution"]["current_product_structure"] in ("assembled", "unavailable")
    assert body["generation_execution"]["llm"] in ("success", "unavailable", "error")
    # every suggestion carries a stamped recommendation_id
    for s in body["suggestions"]:
        assert s["recommendation_id"] and s["recommendation_id"].startswith("rec_")
