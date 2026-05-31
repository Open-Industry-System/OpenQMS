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
                {"id": "n1", "type": "FailureMode", "name": "焊接不良", "severity": 9, "occurrence": 8, "detection": 5},
                {"id": "n2", "type": "FailureMode", "name": "虚焊", "severity": 7, "occurrence": 4, "detection": 3},
                {"id": "n3", "type": "Function", "name": "导电功能"},
            ],
            "edges": []
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
