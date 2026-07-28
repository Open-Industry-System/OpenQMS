import uuid

import pytest

from app.models.fmea import FMEADocument
from app.services.retriever_executions import run_retrievers


class _FakeEmbedding:
    async def embed(self, texts):
        return [[0.01] * 1536 for _ in texts]


@pytest.mark.asyncio
async def test_unavailable_when_no_embedding(db, default_factory, admin_user):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-RET-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    execs, items = await run_retrievers(
        db, None, query_text="焊接", user_product_lines=None,
        fmea_id=fmea.fmea_id, fmea_type="PFMEA",
        product_line_code="DC-DC-100", user=admin_user,
    )
    by_src = {e.source: e for e in execs}
    assert by_src["semantic_search"].status == "unavailable"
    assert by_src["lessons_learned"].status == "unavailable"
    assert items == []


@pytest.mark.asyncio
async def test_status_is_empty_or_success_never_raises(db, default_factory, admin_user):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-RET-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    execs, items = await run_retrievers(
        db, _FakeEmbedding(), query_text="不存在的失效模式xyz", user_product_lines=None,
        fmea_id=fmea.fmea_id, fmea_type="PFMEA",
        product_line_code="DC-DC-100", user=admin_user,
    )
    by_src = {e.source: e for e in execs}
    for name in ("semantic_search", "lessons_learned"):
        assert by_src[name].status in ("success", "empty")
        assert by_src[name].hit_count >= 0 and by_src[name].latency_ms >= 0
    for it in items:
        assert it.source in ("semantic_search", "lessons_learned")
