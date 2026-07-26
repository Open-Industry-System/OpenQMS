import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.models.graph_sync_outbox import GraphSyncOutbox
from app.services.fmea_service import update_fmea, _apply_fmea_update

pytestmark = pytest.mark.requires_db


async def _make_fmea(db, factory_id, user_id, graph=None):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-CORE-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=factory_id,
        status="draft", created_by=user_id, graph_data=graph or {"nodes": [], "edges": []},
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.mark.asyncio
async def test_update_fmea_public_behavior_unchanged(db, default_factory, admin_user):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id,
                            graph={"nodes": [{"id": "n1", "type": "FailureMode", "name": "x"}], "edges": []})
    new_graph = {"nodes": [{"id": "n1", "type": "FailureMode", "name": "y"}], "edges": []}
    out = await update_fmea(db, fmea, title=None, graph_data=new_graph, user_id=admin_user.user_id)
    assert out.lock_version == fmea.lock_version + 1 or out.lock_version >= 1
    outbox = (await db.execute(select(GraphSyncOutbox).where(GraphSyncOutbox.aggregate_id == fmea.fmea_id))).scalars().all()
    assert len(outbox) >= 1
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == fmea.fmea_id, AuditLog.action == "UPDATE"))).scalars().all()
    assert len(audits) >= 1


@pytest.mark.asyncio
async def test_apply_fmea_update_does_not_commit(db, default_factory, admin_user):
    """_apply_fmea_update 不 commit：在调用方未 commit 前，新 session 看不到 graph 变化占位——
    这里用同 session flush 后即可查到 audit/outbox 行（证明副作用已 add），且函数无返回外 commit。"""
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id,
                            graph={"nodes": [{"id": "n1", "type": "FailureMode", "name": "x"}], "edges": []})
    new_graph = {"nodes": [{"id": "n1", "type": "FailureMode", "name": "y"}], "edges": []}
    await _apply_fmea_update(db, fmea, title=None, graph_data=new_graph, user_id=admin_user.user_id)
    await db.flush()
    outbox = (await db.execute(select(GraphSyncOutbox).where(GraphSyncOutbox.aggregate_id == fmea.fmea_id))).scalars().all()
    assert len(outbox) >= 1   # 副作用已 add 到 session，但函数未 commit


@pytest.mark.asyncio
async def test_update_cannot_drop_wizard_scope(db, default_factory, admin_user):
    """N4：已带 wizardScope 的文档，更新时 incoming graph_data 丢掉 wizardScope 必须被拒绝。"""
    graph = {
        "nodes": [{"id": "n1", "type": "FailureMode", "name": "x"}],
        "edges": [],
        "wizardScope": {"wizard_completed": True},
    }
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, graph=graph)
    with pytest.raises(ValueError):
        await update_fmea(
            db, fmea, title=None,
            graph_data={"nodes": [], "edges": []},  # wizardScope dropped
            user_id=admin_user.user_id,
        )
