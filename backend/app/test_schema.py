import sys

from pydantic import ValidationError

from app.schemas.fmea import GraphNodeSchema


def test_graph_node_schema_backward_compatibility():
    # 1. Test traditional node (backward compatibility)
    node_data = {
        "id": "n1",
        "type": "Process",
        "name": "SMT贴装",
        "process_number": "OP10",
        "severity": 7,
        "occurrence": 4,
        "detection": 3
    }
    node = GraphNodeSchema(**node_data)
    assert node.id == "n1"
    assert node.classification is None
    assert node.severity_plant is None
    assert node.revised_severity == 0
    print("Pass: Traditional backward compatible schema validation")

def test_graph_node_schema_pfmea_fields():
    # 2. Test PFMEA specific node with 3-segment severity
    node_data = {
        "id": "fe_1",
        "type": "FailureEffect",
        "name": "电控板功能丧失",
        "severity": 8,
        "severity_plant": 4,
        "severity_customer": 8,
        "severity_user": 8,
        "occurrence": 0,
        "detection": 0,
        "responsible": "张工",
        "status": "open"
    }
    node = GraphNodeSchema(**node_data)
    assert node.severity == 8
    assert node.severity_plant == 4
    assert node.severity_customer == 8
    assert node.severity_user == 8
    assert node.responsible == "张工"
    assert node.status == "open"
    print("Pass: New PFMEA 3-segment severity schema validation")

def test_invalid_range_validation():
    # 3. Test validation constraint boundaries (severity ge 0 le 10)
    node_data = {
        "id": "fe_1",
        "type": "FailureEffect",
        "name": "电控板功能丧失",
        "severity": 12,  # Invalid
        "occurrence": 0,
        "detection": 0
    }
    try:
        GraphNodeSchema(**node_data)
        assert False, "Should have failed validation"
    except ValidationError:
        print("Pass: Invalid range constraint caught successfully")

if __name__ == "__main__":
    try:
        test_graph_node_schema_backward_compatibility()
        test_graph_node_schema_pfmea_fields()
        test_invalid_range_validation()
        print("\nAll schema validations passed perfectly!")
        sys.exit(0)
    except Exception as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
