"""Tests for dashboard pending_breakdown (仪表盘「待办事项」下钻分项计数)."""
import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-non-default-secret-key")

import pytest

from app.models.fmea import FMEADocument

import app.models  # noqa: F401 — register all FK-referenced tables


def _pl_code() -> str:
    """Unique product_line_code per test (not an FK; no ProductLine row needed)."""
    return "T" + uuid.uuid4().hex[:12]


def _make_fmea(document_no, product_line_code, status, factory_id, created_by):
    return FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=document_no,
        title=f"doc-{document_no}",
        fmea_type="PFMEA",
        product_line_code=product_line_code,
        factory_id=factory_id,
        created_by=created_by,
        status=status,
        graph_data={"nodes": [], "edges": []},
    )


@pytest.mark.asyncio
async def test_get_summary_pending_breakdown_counts_fmea(db, default_factory, admin_user):
    """get_summary 返回 pending_breakdown；fmea 项 = draft + in_review 计数。"""
    from app.services.dashboard_service import get_summary

    pl = _pl_code()
    docs = [
        _make_fmea(f"PFMEA-{uuid.uuid4().hex[:8]}", pl, "draft", default_factory.id, admin_user.user_id),
        _make_fmea(f"PFMEA-{uuid.uuid4().hex[:8]}", pl, "in_review", default_factory.id, admin_user.user_id),
        _make_fmea(f"PFMEA-{uuid.uuid4().hex[:8]}", pl, "approved", default_factory.id, admin_user.user_id),
    ]
    db.add_all(docs)
    await db.flush()

    summary = await get_summary(db, product_line=pl, factory_id=default_factory.id)
    bd = summary["pending_breakdown"]
    assert bd["fmea"] == 2
    # 结构完整：capa / complaint 键存在；本用例未建对应行，应为 0
    assert bd["capa"] == 0
    assert bd["complaint"] == 0
    # 合计 = 三者之和
    assert summary["pending_actions"] == bd["fmea"] + bd["capa"] + bd["complaint"]


@pytest.mark.asyncio
async def test_get_widgets_data_propagates_pending_breakdown(monkeypatch):
    """get_widgets_data 把 get_summary 的 pending_breakdown 透传到 kpi。"""
    from app.services import dashboard_service

    async def fake_get_summary(db, **kwargs):
        return {
            "pending_actions": 12,
            "overdue_tasks": 2,
            "high_risk_items": 1,
            "month_trend": 3,
            "pending_breakdown": {"fmea": 3, "capa": 5, "complaint": 4},
        }

    monkeypatch.setattr(dashboard_service, "get_summary", fake_get_summary)

    result = await dashboard_service.get_widgets_data(
        db=object(),
        types=["kpi_pending_actions"],
        product_line_codes=["PL1"],
        user_id="user-1",
    )

    assert result["kpi"]["pending_breakdown"] == {"fmea": 3, "capa": 5, "complaint": 4}
    assert result["kpi"]["pending_actions"] == 12
