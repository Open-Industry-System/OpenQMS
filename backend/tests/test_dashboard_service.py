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
