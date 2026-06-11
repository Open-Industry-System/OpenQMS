"""Unit tests for cp_validation rule engine."""
import uuid
import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.cp_validation.rule_engine import (
    rule_r001_control_method,
    rule_r002_reaction_plan,
    rule_r003_fmea_consistency,
    rule_r004_special_class,
    run_all_rules,
    _stable_key,
)


class FakeItem:
    def __init__(self, **kwargs):
        self.item_id = kwargs.get("item_id", uuid.uuid4())
        self.step_no = kwargs.get("step_no", "")
        self.process_name = kwargs.get("process_name", "")
        self.control_method = kwargs.get("control_method", "")
        self.reaction_plan = kwargs.get("reaction_plan", "")
        self.special_class = kwargs.get("special_class", "")
        self.evaluation_method = kwargs.get("evaluation_method", "")
        self.source_fmea_node_id = kwargs.get("source_fmea_node_id", None)
        self.product_characteristic = kwargs.get("product_characteristic", "")
        self.process_characteristic = kwargs.get("process_characteristic", "")
        self.sort_order = kwargs.get("sort_order", 0)


# ─── stable_key ─────────────────────────────────────────────────────────────

def test_stable_key_uses_fmea_node_id_and_characteristic():
    item = FakeItem(source_fmea_node_id="node-1", step_no="10", product_characteristic="尺寸A")
    assert _stable_key(item) == "node-1|尺寸A"


def test_stable_key_falls_back_to_step_no_and_sort_order():
    item = FakeItem(source_fmea_node_id=None, step_no="20", sort_order=3)
    assert _stable_key(item) == "20|#3"


def test_stable_key_distinguishes_same_fmea_node_different_characteristic():
    """Two CP items sharing the same FMEA ProcessStep but different characteristics
    must produce different stable_key (and thus different findings)."""
    item_a = FakeItem(source_fmea_node_id="node-1", product_characteristic="尺寸A", control_method="")
    item_b = FakeItem(source_fmea_node_id="node-1", product_characteristic="尺寸B", control_method="")
    assert _stable_key(item_a) != _stable_key(item_b)

    findings_a, _ = rule_r001_control_method([item_a])
    findings_b, _ = rule_r001_control_method([item_b])
    assert len(findings_a) == 1
    assert len(findings_b) == 1
    assert findings_a[0].stable_key != findings_b[0].stable_key


# ─── R001 ───────────────────────────────────────────────────────────────────

def test_r001_detects_empty_control_method():
    items = [FakeItem(source_fmea_node_id="n1", control_method="")]
    findings, failed = rule_r001_control_method(items)
    assert len(findings) == 1
    assert findings[0].rule_id == "R001"
    assert findings[0].severity == "error"
    assert findings[0].stable_key == "n1|#0"


def test_r001_ignores_valid_control_method():
    items = [FakeItem(control_method="X-bar R chart")]
    findings, _ = rule_r001_control_method(items)
    assert len(findings) == 0


def test_r001_detects_placeholder_sop():
    items = [FakeItem(source_fmea_node_id="n1", control_method="见SOP")]
    findings, _ = rule_r001_control_method(items)
    assert len(findings) == 1


# ─── R002 ───────────────────────────────────────────────────────────────────

def test_r002_detects_empty_reaction_plan():
    items = [FakeItem(source_fmea_node_id="n1", reaction_plan="")]
    findings, _ = rule_r002_reaction_plan(items)
    assert len(findings) == 1
    assert findings[0].rule_id == "R002"


# ─── R003 ───────────────────────────────────────────────────────────────────

def test_r003_detects_deleted_fmea_node():
    items = [FakeItem(step_no="10", process_name="焊接", source_fmea_node_id="node-1")]
    fmea_graph = {"nodes": [], "edges": []}
    findings, _ = rule_r003_fmea_consistency(items, fmea_graph)
    assert len(findings) == 1
    assert findings[0].title == "FMEA源工序已删除"


def test_r003_detects_name_mismatch():
    items = [FakeItem(step_no="10", process_name="旧名称", source_fmea_node_id="node-1")]
    fmea_graph = {
        "nodes": [{"id": "node-1", "type": "ProcessStep", "process_number": "10", "name": "新名称"}],
        "edges": [],
    }
    findings, _ = rule_r003_fmea_consistency(items, fmea_graph)
    assert len(findings) == 1
    assert "不一致" in findings[0].title


def test_r003_passes_matching():
    items = [FakeItem(step_no="10", process_name="焊接", source_fmea_node_id="node-1")]
    fmea_graph = {
        "nodes": [{"id": "node-1", "type": "ProcessStep", "process_number": "10", "name": "焊接"}],
        "edges": [],
    }
    findings, _ = rule_r003_fmea_consistency(items, fmea_graph)
    assert len(findings) == 0


def test_r003_empty_graph_returns_empty():
    findings, _ = rule_r003_fmea_consistency([FakeItem(source_fmea_node_id="n1")], None)
    assert len(findings) == 0


# ─── R004 ───────────────────────────────────────────────────────────────────

def test_r004_detects_cc_missing_methods():
    items = [FakeItem(step_no="10", special_class="CC", evaluation_method="", control_method="")]
    findings, _ = rule_r004_special_class(items)
    assert len(findings) == 1
    assert "CC" in findings[0].description


def test_r004_passes_when_methods_present():
    items = [FakeItem(special_class="CC", evaluation_method="目视检查", control_method="SPC")]
    findings, _ = rule_r004_special_class(items)
    assert len(findings) == 0


def test_r004_ignores_non_special():
    items = [FakeItem(special_class="", evaluation_method="", control_method="")]
    findings, _ = rule_r004_special_class(items)
    assert len(findings) == 0


# ─── run_all_rules ──────────────────────────────────────────────────────────

def test_run_all_rules_returns_all_findings():
    items = [
        FakeItem(step_no="10", control_method="", reaction_plan="", special_class="CC"),
    ]
    findings, failed = run_all_rules(None, items, None)
    assert len(findings) == 3  # R001 + R002 + R004
    assert failed == []
