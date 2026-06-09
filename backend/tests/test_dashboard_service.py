import os

os.environ.setdefault("SECRET_KEY", "test-non-default-secret-key")

import pytest
from app.utils.fmea_graph import build_rpn_rows


class TestBuildRPNRows:
    def test_single_cause_effect_chain(self):
        nodes = [
            {"id": "fm1", "type": "FailureMode", "name": "FM1", "severity": 0, "occurrence": 0, "detection": 0},
            {"id": "fe1", "type": "FailureEffect", "name": "FE1", "severity": 8, "occurrence": 0, "detection": 0},
            {"id": "fc1", "type": "FailureCause", "name": "FC1", "severity": 0, "occurrence": 4, "detection": 0},
            {"id": "dc1", "type": "DetectionControl", "name": "DC1", "severity": 0, "occurrence": 0, "detection": 3},
        ]
        edges = [
            {"source": "fm1", "target": "fe1", "type": "EFFECT_OF"},
            {"source": "fc1", "target": "fm1", "type": "CAUSE_OF"},
            {"source": "fc1", "target": "dc1", "type": "DETECTED_BY"},
        ]
        rows = build_rpn_rows(nodes, edges)
        assert len(rows) == 1
        assert rows[0]["severity"] == 8
        assert rows[0]["occurrence"] == 4
        assert rows[0]["detection"] == 3

    def test_multiple_causes_one_effect(self):
        nodes = [
            {"id": "fm1", "type": "FailureMode", "name": "FM1"},
            {"id": "fe1", "type": "FailureEffect", "name": "FE1", "severity": 10},
            {"id": "fc1", "type": "FailureCause", "name": "FC1", "occurrence": 3},
            {"id": "fc2", "type": "FailureCause", "name": "FC2", "occurrence": 5},
        ]
        edges = [
            {"source": "fm1", "target": "fe1", "type": "EFFECT_OF"},
            {"source": "fc1", "target": "fm1", "type": "CAUSE_OF"},
            {"source": "fc2", "target": "fm1", "type": "CAUSE_OF"},
        ]
        rows = build_rpn_rows(nodes, edges)
        assert len(rows) == 2
        assert rows[0]["severity"] == 10
        assert rows[1]["severity"] == 10

    def test_empty_graph(self):
        assert build_rpn_rows([], []) == []

    def test_no_causes_uses_detection_from_fm(self):
        nodes = [
            {"id": "fm1", "type": "FailureMode", "name": "FM1"},
            {"id": "fe1", "type": "FailureEffect", "name": "FE1", "severity": 5},
            {"id": "dc1", "type": "DetectionControl", "name": "DC1", "detection": 2},
        ]
        edges = [
            {"source": "fm1", "target": "fe1", "type": "EFFECT_OF"},
            {"source": "fm1", "target": "dc1", "type": "DETECTED_BY"},
        ]
        rows = build_rpn_rows(nodes, edges)
        assert len(rows) == 1
        assert rows[0]["severity"] == 5
        assert rows[0]["occurrence"] == 0
        assert rows[0]["detection"] == 2


@pytest.mark.asyncio
async def test_get_widgets_data_returns_only_requested_alert_payloads(monkeypatch):
    from app.services import dashboard_service

    async def fake_get_alerts(db, product_line_codes=None):
        return {
            "high_rpn_fmeas": [{"document_no": "PFMEA-1"}],
            "overdue_capas": [{"document_no": "8D-1"}],
            "high_ppm_suppliers": [{"supplier_name": "Supplier A"}],
        }

    monkeypatch.setattr(dashboard_service, "get_alerts", fake_get_alerts)

    result = await dashboard_service.get_widgets_data(
        db=object(),
        types=["alert_high_rpn_fmea"],
        product_line_codes=["PL1"],
        user_id="user-1",
    )

    assert result["alerts"] == {"high_rpn_fmeas": [{"document_no": "PFMEA-1"}]}


@pytest.mark.asyncio
async def test_get_widgets_data_counts_only_latest_mes_equipment_status_rows():
    from sqlalchemy.dialects import postgresql
    from app.services import dashboard_service

    class Result:
        def all(self):
            return []

    class DB:
        async def execute(self, query):
            sql = str(query.compile(dialect=postgresql.dialect()))
            assert "row_number() OVER" in sql
            assert "PARTITION BY mes_equipment_status.connection_id, mes_equipment_status.equipment_code" in sql
            assert "ORDER BY mes_equipment_status.recorded_at DESC" in sql
            assert "mes_equipment_status.product_line_code IN" in sql
            assert "anon_1.rn =" in sql
            return Result()

    result = await dashboard_service.get_widgets_data(
        db=DB(),
        types=["mes_equipment_status"],
        product_line_codes=["PL1"],
        user_id="user-1",
    )

    assert result["errors"] == {}
