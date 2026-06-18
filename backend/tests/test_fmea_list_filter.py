"""Tests for list_fmeas fmea_type / search / high_rpn combination filtering.

Isolation: each test uses a unique product_line_code + UUID-suffixed document_no
and passes product_line=<that code> to list_fmeas, so counts are independent of
any pre-existing/seeded FMEA rows in the test database. The `db` fixture rolls
back each test's transaction.
"""
import uuid

from app.models.fmea import FMEADocument
from app.services.fmea_service import list_fmeas

import app.models  # noqa: F401 — register all FK-referenced tables


def _pl_code() -> str:
    """Unique product_line_code per test (not an FK; no ProductLine row needed)."""
    return "T" + uuid.uuid4().hex[:12]  # 13 chars, fits String(20)


def _make_doc(document_no: str, title: str, product_line_code: str,
              fmea_type: str = "PFMEA", graph_data: dict | None = None,
              factory_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
              created_by=uuid.UUID("00000000-0000-0000-0000-000000000002")):
    return FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=document_no,
        title=title,
        fmea_type=fmea_type,
        product_line_code=product_line_code,
        factory_id=factory_id,
        created_by=created_by,
        status="draft",
        graph_data=graph_data or {"nodes": [], "edges": []},
    )


async def test_fmea_type_filter(db, default_factory, admin_user):
    pl = _pl_code()
    pfmea = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "过程 FMEA", pl, "PFMEA", factory_id=default_factory.id, created_by=admin_user.user_id)
    dfmea = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "设计 FMEA", pl, "DFMEA", factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([pfmea, dfmea])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, fmea_type="PFMEA"
    )
    assert total == 1
    assert items[0].document_no == pfmea.document_no


async def test_search_by_document_no_case_insensitive(db, default_factory, admin_user):
    pl = _pl_code()
    a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Alpha", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    b = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "Beta", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([a, b])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, search="pfmea"
    )
    assert total == 1
    assert items[0].document_no == a.document_no


async def test_search_by_title(db, default_factory, admin_user):
    pl = _pl_code()
    a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "焊接工艺失效分析", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    b = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "Other", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([a, b])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, search="焊接"
    )
    assert total == 1
    assert items[0].title == "焊接工艺失效分析"


async def test_search_blank_skips_filter(db, default_factory, admin_user):
    pl = _pl_code()
    a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Alpha", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    b = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "Beta", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([a, b])
    await db.flush()

    _, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, search="   "
    )
    assert total == 2


async def test_search_escapes_sql_wildcards(db, default_factory, admin_user):
    pl = _pl_code()
    a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Alpha", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    b = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "100%_yield", pl, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add_all([a, b])
    await db.flush()

    # "%" and "_" are escaped → literal match, only b's title contains "%"
    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, search="%"
    )
    assert total == 1
    assert items[0].title == "100%_yield"


def _graph(severity: int, occurrence: int, detection: int):
    """A 3-node-per-role graph; build_rpn_rows yields S×O×D from these."""
    return {
        "nodes": [
            {"id": "fm_1", "type": "FailureMode", "name": "偏移"},
            {"id": "fe_1", "type": "FailureEffect", "name": "失效后果", "severity": severity},
            {"id": "fc_1", "type": "FailureCause", "name": "原因", "occurrence": occurrence},
            {"id": "dc_1", "type": "DetectionControl", "name": "探测", "detection": detection},
        ],
        "edges": [
            {"source": "fm_1", "target": "fe_1", "type": "EFFECT_OF"},
            {"source": "fc_1", "target": "fm_1", "type": "CAUSE_OF"},
            {"source": "fc_1", "target": "dc_1", "type": "DETECTED_BY"},
        ],
    }


def _high_rpn_graph():
    return _graph(8, 3, 6)  # 144 ≥ 100


def _low_rpn_graph():
    return _graph(2, 2, 2)  # 8 < 100


async def test_high_rpn_with_fmea_type_filters_first(db, default_factory, admin_user):
    pl = _pl_code()
    high_pfmea = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "High PFMEA", pl, "PFMEA", _high_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    high_dfmea = _make_doc(f"DFMEA-{uuid.uuid4().hex[:8]}", "High DFMEA", pl, "DFMEA", _high_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    low_pfmea = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Low PFMEA", pl, "PFMEA", _low_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    db.add_all([high_pfmea, high_dfmea, low_pfmea])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, high_rpn=True, fmea_type="PFMEA"
    )
    # 只剩 PFMEA（fmea_type 过滤掉 DFMEA），再按 RPN 排除 low_pfmea
    assert total == 1
    assert items[0].fmea_type == "PFMEA"
    assert items[0].document_no == high_pfmea.document_no


async def test_high_rpn_with_search_filters_first(db, default_factory, admin_user):
    pl = _pl_code()
    h_a = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "焊接失效", pl, "PFMEA", _high_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    h_b = _make_doc(f"PFMEA-{uuid.uuid4().hex[:8]}", "Other", pl, "PFMEA", _high_rpn_graph(), default_factory.id, created_by=admin_user.user_id)
    db.add_all([h_a, h_b])
    await db.flush()

    items, total = await list_fmeas(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, high_rpn=True, search="焊接"
    )
    assert total == 1
    assert items[0].title == "焊接失效"
