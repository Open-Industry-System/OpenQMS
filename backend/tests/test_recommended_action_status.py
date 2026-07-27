import pytest
from unittest.mock import AsyncMock, patch
from app.services.recommended_action_status import normalize_action_status


@pytest.mark.parametrize("legacy,expected", [
    ("undecided", "open"), ("planned", "in_progress"), ("done", "completed"),
    ("notExecuted", "not_executed"), ("closed", "completed"),
    ("open", "open"), ("in_progress", "in_progress"),
    ("completed", "completed"), ("not_executed", "not_executed"),
    (None, None), ("", None), ("bogus", None),
])
def test_normalize_action_status(legacy, expected):
    assert normalize_action_status(legacy) == expected


@pytest.mark.asyncio
@patch("app.services.fmea_service.enqueue_embedding", new_callable=AsyncMock)
async def test_update_fmea_normalizes_action_status(_mock_enqueue, db, default_factory, admin_user):
    """缺陷修复 #2：normalize_action_status 定义了但零 import → 落库仍是 legacy planned。
    期望：update_fmea 保存时 RecommendedAction.status 归一为 canonical。"""
    import uuid
    from app.models.fmea import FMEADocument
    from app.services.fmea_service import update_fmea
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-NORM-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1, created_by=admin_user.user_id,
    )
    db.add(fmea)
    await db.commit()
    graph = {
        "nodes": [
            {"id": "ra1", "type": "RecommendedAction", "name": "a", "status": "planned"},
            {"id": "ra2", "type": "RecommendedAction", "name": "b", "status": "done"},
            {"id": "ra3", "type": "RecommendedAction", "name": "c", "status": "notExecuted"},
            {"id": "ra4", "type": "RecommendedAction", "name": "d", "status": "open"},
            {"id": "fm1", "type": "FailureMode", "name": "x"},
        ],
        "edges": [],
    }
    await update_fmea(db, fmea, None, graph, admin_user.user_id)
    await db.refresh(fmea)
    nodes = {n["id"]: n for n in fmea.graph_data["nodes"]}
    assert nodes["ra1"]["status"] == "in_progress", f"planned→? got {nodes['ra1']['status']}"
    assert nodes["ra2"]["status"] == "completed", f"done→? got {nodes['ra2']['status']}"
    assert nodes["ra3"]["status"] == "not_executed", f"notExecuted→? got {nodes['ra3']['status']}"
    assert nodes["ra4"]["status"] == "open", f"open→? got {nodes['ra4']['status']}"
    # 非 RecommendedAction 节点不受影响
    assert "status" not in nodes["fm1"]


@pytest.mark.asyncio
@patch("app.services.fmea_service.enqueue_embedding", new_callable=AsyncMock)
async def test_put_with_adoptions_writes_audit(_mock_enqueue, admin_client, db, default_factory, admin_user):
    import uuid
    from sqlalchemy import select
    from app.models.audit import AuditLog
    from app.models.fmea import FMEADocument
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-PUT-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    resp = await admin_client.put(
        f"/api/fmea/{fmea.fmea_id}",
        json={"adoptions": [{
            "field_id": "fm1", "recommendation_id": "rec_e2e_1",
            "source": "graph", "stage_index": 0, "adopted_text": "焊接电流不足",
        }]},
    )
    assert resp.status_code == 200
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert any(r.changed_fields.get("recommendation_id") == "rec_e2e_1" for r in rows)

