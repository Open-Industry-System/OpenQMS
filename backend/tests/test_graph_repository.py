import types
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.graph.jsonb_repository import JSONBRepository
from app.state_machines.fmea_state import compute_ap


def test_compute_ap_consistency_with_frontend_matrix():
    """验证 compute_ap 与前端 AIAG-VDA 矩阵一致。"""
    assert compute_ap(10, 10, 10) == "H"
    assert compute_ap(1, 1, 1) == "L"
    assert compute_ap(9, 3, 7) == "H"
    assert compute_ap(9, 3, 5) == "M"
    assert compute_ap(9, 3, 4) == "L"
    assert compute_ap(7, 6, 2) == "H"
    assert compute_ap(7, 6, 1) == "M"
    assert compute_ap(4, 8, 5) == "H"
    assert compute_ap(4, 8, 4) == "M"
    assert compute_ap(3, 8, 5) == "M"
    assert compute_ap(3, 8, 4) == "L"


def _make_mock_fmea(**kwargs):
    """用 SimpleNamespace 构建稳定的 mock FMEA 对象，避免 AsyncMock 属性漂移。"""
    return types.SimpleNamespace(**kwargs)


@pytest.mark.asyncio
async def test_jsonb_repository_stats_field_structure():
    """验证 JSONBRepository stats 返回字段结构完整且 ap_distribution 含全键。"""
    mock_fmea = _make_mock_fmea(
        fmea_id="test-fmea-id",
        document_no="PFMEA-2026-001",
        graph_data={
            "nodes": [
                {"id": "n1", "type": "FailureMode", "name": "焊接不良"},
                {"id": "n2", "type": "FailureMode", "name": "虚焊"},
                {"id": "n3", "type": "Function", "name": "导电功能"},
                {"id": "e1", "type": "FailureEffect", "name": "开裂", "severity": 9},
                {"id": "e2", "type": "FailureEffect", "name": "断裂", "severity": 7},
                {"id": "c1", "type": "FailureCause", "name": "温度高", "occurrence": 8},
                {"id": "c2", "type": "FailureCause", "name": "压力不足", "occurrence": 4},
                {"id": "d1", "type": "DetectionControl", "name": "目检", "detection": 5},
                {"id": "d2", "type": "DetectionControl", "name": "X光", "detection": 3},
            ],
            "edges": [
                {"source": "n1", "target": "e1", "type": "EFFECT_OF"},
                {"source": "n2", "target": "e2", "type": "EFFECT_OF"},
                {"source": "c1", "target": "n1", "type": "CAUSE_OF"},
                {"source": "c2", "target": "n2", "type": "CAUSE_OF"},
                {"source": "c1", "target": "d1", "type": "DETECTED_BY"},
                {"source": "c2", "target": "d2", "type": "DETECTED_BY"},
            ],
        },
    )

    # SQLAlchemy result.scalars().all() 是同步链，用 MagicMock
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [mock_fmea]

    mock_db = AsyncMock()
    mock_db.execute.return_value = result_mock

    repo = JSONBRepository(mock_db)
    data = await repo.get_cross_fmea_stats("DC-DC-100")

    assert "total_fmeas" in data
    assert "total_nodes" in data
    assert "node_type_distribution" in data
    assert "ap_distribution" in data
    assert "high_ap_nodes" in data
    assert "avg_rpn" in data
    assert "top_failure_modes" in data

    # ap_distribution 必须含全键
    ap = data["ap_distribution"]
    assert ap == {"H": 1, "M": 1, "L": 0}  # n1=H, n2=M

    # high_ap_nodes 按 RPN 降序
    rpns = [n["rpn"] for n in data["high_ap_nodes"]]
    assert rpns == sorted(rpns, reverse=True)

    # top_failure_modes 含 document_no
    assert data["top_failure_modes"][0]["document_no"] == "PFMEA-2026-001"


@pytest.mark.asyncio
async def test_jsonb_repository_stats_empty_sod_handling():
    """验证空 S/O/D 时跳过 AP 计算、RPN=0。"""
    mock_fmea = _make_mock_fmea(
        fmea_id="test-fmea-id",
        document_no="PFMEA-2026-001",
        graph_data={
            "nodes": [
                {"id": "n1", "type": "FailureMode", "name": "无数据", "severity": 0, "occurrence": 0, "detection": 0},
            ],
            "edges": []
        },
    )

    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [mock_fmea]

    mock_db = AsyncMock()
    mock_db.execute.return_value = result_mock

    repo = JSONBRepository(mock_db)
    data = await repo.get_cross_fmea_stats("DC-DC-100")

    assert data["ap_distribution"] == {"H": 0, "M": 0, "L": 0}
    assert data["avg_rpn"] == 0
    assert data["high_ap_nodes"] == []


import uuid as _uuid


def _mock_fmea_global(document_no, product_line_code, graph_data):
    """构造 mock FMEADocument（复用现有文件中的 _make_mock_fmea 风格）。"""
    return types.SimpleNamespace(
        fmea_id=_uuid.uuid4(),
        document_no=document_no,
        product_line_code=product_line_code,
        graph_data=graph_data,
    )


@pytest.mark.asyncio
async def test_jsonb_get_cross_fmea_stats_top_failure_modes_has_document_no():
    """验证 JSONB get_cross_fmea_stats 的 top_failure_modes 包含 document_no。"""
    mock_db = AsyncMock()
    result_mock = MagicMock()

    # 图数据必须包含 DetectionControl + DETECTED_BY，否则 D=0 → RPN=0
    fmea = _mock_fmea_global(
        document_no="PFMEA-2026-001",
        product_line_code="DC-DC-100",
        graph_data={
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": "焊接不良"},
                {"id": "e1", "type": "FailureEffect", "name": "开裂", "severity": 8},
                {"id": "c1", "type": "FailureCause", "name": "温度高", "occurrence": 5},
                {"id": "d1", "type": "DetectionControl", "name": "目检", "detection": 4},
            ],
            "edges": [
                {"source": "fm1", "target": "e1", "type": "EFFECT_OF"},
                {"source": "c1", "target": "fm1", "type": "CAUSE_OF"},
                {"source": "c1", "target": "d1", "type": "DETECTED_BY"},
            ],
        },
    )

    result_mock.scalars.return_value.all.return_value = [fmea]
    mock_db.execute.return_value = result_mock

    repo = JSONBRepository(mock_db)
    stats = await repo.get_cross_fmea_stats("DC-DC-100")

    assert "top_failure_modes" in stats
    assert len(stats["top_failure_modes"]) == 1
    assert stats["top_failure_modes"][0]["document_no"] == "PFMEA-2026-001"


@pytest.mark.asyncio
async def test_jsonb_get_global_stats_aggregates_all_product_lines():
    """验证 JSONB get_global_stats 聚合所有产品线，不限制 product_line_code。"""
    mock_db = AsyncMock()
    result_mock = MagicMock()

    fmea_a = _mock_fmea_global(
        document_no="PFMEA-2026-001",
        product_line_code="DC-DC-100",
        graph_data={
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": "焊接不良"},
                {"id": "e1", "type": "FailureEffect", "name": "开裂", "severity": 8},
                {"id": "c1", "type": "FailureCause", "name": "温度高", "occurrence": 5},
                {"id": "d1", "type": "DetectionControl", "name": "目检", "detection": 4},
            ],
            "edges": [
                {"source": "fm1", "target": "e1", "type": "EFFECT_OF"},
                {"source": "c1", "target": "fm1", "type": "CAUSE_OF"},
                {"source": "c1", "target": "d1", "type": "DETECTED_BY"},
            ],
        },
    )
    fmea_b = _mock_fmea_global(
        document_no="PFMEA-2026-002",
        product_line_code="DC-DC-200",
        graph_data={
            "nodes": [
                {"id": "fm2", "type": "FailureMode", "name": "密封失效"},
                {"id": "e2", "type": "FailureEffect", "name": "漏水", "severity": 7},
                {"id": "c2", "type": "FailureCause", "name": "老化", "occurrence": 4},
                {"id": "d2", "type": "DetectionControl", "name": "气密测试", "detection": 3},
            ],
            "edges": [
                {"source": "fm2", "target": "e2", "type": "EFFECT_OF"},
                {"source": "c2", "target": "fm2", "type": "CAUSE_OF"},
                {"source": "c2", "target": "d2", "type": "DETECTED_BY"},
            ],
        },
    )

    result_mock.scalars.return_value.all.return_value = [fmea_a, fmea_b]
    mock_db.execute.return_value = result_mock

    repo = JSONBRepository(mock_db)
    stats = await repo.get_global_stats()

    # 聚合两个产品线的全部文档
    assert stats["total_fmeas"] == 2
    # 两个 FMEA 的 FailureMode 都因 RPN>0 进入 top_failure_modes
    assert len(stats["top_failure_modes"]) == 2
    # 验证两份文档的 document_no 都在结果中
    doc_nos = {tm["document_no"] for tm in stats["top_failure_modes"]}
    assert doc_nos == {"PFMEA-2026-001", "PFMEA-2026-002"}
    # top_failure_modes 均包含 document_no（Task 1 修复）
    for tm in stats["top_failure_modes"]:
        assert "document_no" in tm
