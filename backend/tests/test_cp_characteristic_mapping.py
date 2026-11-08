from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest


FMEA_ID = UUID("00000000-0000-0000-0000-000000000001")
ITEM_ID = UUID("00000000-0000-0000-0000-000000000099")
PRODUCT_IDS = (
    "00000000-0000-0000-0000-000000000101",
    "00000000-0000-0000-0000-000000000102",
)
PROCESS_IDS = (
    "00000000-0000-0000-0000-000000000201",
    "00000000-0000-0000-0000-000000000202",
    "00000000-0000-0000-0000-000000000203",
)


@pytest.fixture
def product_process_graph() -> dict:
    return {
        "nodes": [
            {"id": "s1", "type": "ProcessStep", "name": "装配", "process_number": "OP10"},
            {
                "id": "w1",
                "type": "ProcessWorkElement",
                "name": "装配机",
                "classification": "Machine",
            },
            {
                "id": "sf1",
                "type": "ProcessStepFunction",
                "name": "确保产品尺寸",
                "characteristics": [
                    {
                        "id": PRODUCT_IDS[0],
                        "kind": "product",
                        "name": "孔距",
                        "specification": "10.0±0.1 mm",
                        "classification": "CC",
                    },
                    {
                        "id": PRODUCT_IDS[1],
                        "kind": "product",
                        "name": "平面度",
                        "specification": "≤0.05 mm",
                        "classification": "SC",
                    },
                ],
            },
            {
                "id": "wf1",
                "type": "ProcessWorkElementFunction",
                "name": "控制装配过程",
                "characteristics": [
                    {
                        "id": PROCESS_IDS[0],
                        "kind": "process",
                        "name": "装配压力",
                        "specification": "3.0±0.5 bar",
                        "classification": "CC",
                        "related_product_characteristic_ids": list(PRODUCT_IDS),
                    },
                    {
                        "id": PROCESS_IDS[1],
                        "kind": "process",
                        "name": "压装速度",
                        "specification": "20±2 mm/s",
                        "classification": None,
                        "related_product_characteristic_ids": [PRODUCT_IDS[0]],
                    },
                    {
                        "id": PROCESS_IDS[2],
                        "kind": "process",
                        "name": "保持时间",
                        "specification": "2 s",
                        "classification": "SC",
                    },
                ],
            },
        ],
        "edges": [
            {"source": "s1", "target": "sf1", "type": "HAS_FUNCTION"},
            {"source": "s1", "target": "w1", "type": "HAS_WORK_ELEMENT"},
            {"source": "w1", "target": "wf1", "type": "HAS_FUNCTION"},
            {"source": "sf1", "target": "wf1", "type": "FUNCTION_MAPPED_TO"},
        ],
    }


def map_items(graph: dict, *, step_ids: tuple[str, ...] = ("s1",), fmea_type: str = "PFMEA"):
    from app.services.cp_characteristic_mapping import derive_cp_items

    return derive_cp_items(
        fmea_id=FMEA_ID,
        fmea_type=fmea_type,
        graph=graph,
        step_ids=step_ids,
    )


def test_two_product_three_process_yield_five_independent_rows(product_process_graph):
    result = map_items(product_process_graph)

    assert not any(issue.blocking for issue in result.issues)
    assert len(result.items) == 5
    assert sum(bool(item.fields.get("product_characteristic")) for item in result.items) == 2
    assert sum(bool(item.fields.get("process_characteristic")) for item in result.items) == 3
    assert all(
        not (item.fields.get("product_characteristic") and item.fields.get("process_characteristic"))
        for item in result.items
    )
    assert [item.fields["product_characteristic"] or item.fields["process_characteristic"] for item in result.items] == [
        "孔距", "平面度", "装配压力", "压装速度", "保持时间",
    ]


def test_mapping_copies_each_characteristic_specification_classification_and_unambiguous_machine(product_process_graph):
    result = map_items(product_process_graph)

    assert result.items[0].fields == {
        "step_no": "OP10",
        "process_name": "装配",
        "equipment": "装配机",
        "product_characteristic": "孔距",
        "process_characteristic": None,
        "specification_tolerance": "10.0±0.1 mm",
        "special_class": "CC",
    }
    assert result.items[3].fields == {
        "step_no": "OP10",
        "process_name": "装配",
        "equipment": "装配机",
        "product_characteristic": None,
        "process_characteristic": "压装速度",
        "specification_tolerance": "20±2 mm/s",
        "special_class": None,
    }
    assert result.items[0].source_ref.function_id == "sf1"
    assert result.items[0].source_ref.work_element_id is None
    assert result.items[2].source_ref.function_id == "wf1"
    assert result.items[2].source_ref.work_element_id == "w1"
    assert all(item.source_ref.accepted_source_version_id is None for item in result.items)


def test_process_characteristic_without_product_relation_is_a_warning_not_a_cartesian_expansion(product_process_graph):
    result = map_items(product_process_graph)

    assert len(result.items) == 5
    assert [(issue.code, issue.node_id, issue.blocking) for issue in result.issues] == [
        ("missing_product_relation", "wf1", False),
    ]


def test_ambiguous_product_machine_ownership_leaves_equipment_empty_and_warns(product_process_graph):
    graph = deepcopy(product_process_graph)
    graph["nodes"].append(
        {"id": "w2", "type": "ProcessWorkElement", "name": "备用装配机", "classification": "Machine"}
    )
    graph["edges"].append({"source": "s1", "target": "w2", "type": "HAS_WORK_ELEMENT"})

    result = map_items(graph)

    assert [item.fields["equipment"] for item in result.items[:2]] == [None, None]
    assert [(issue.code, issue.node_id, issue.blocking) for issue in result.issues] == [
        ("ambiguous_product_equipment", "sf1", False),
        ("missing_product_relation", "wf1", False),
    ]


def test_legacy_free_text_function_is_blocking_and_does_not_fabricate_a_characteristic(product_process_graph):
    graph = deepcopy(product_process_graph)
    graph["nodes"][2].pop("characteristics")
    graph["nodes"][2].update({"requirement": "历史要求", "specification": "历史规范", "classification": "CC"})

    result = map_items(graph)

    assert result.items == ()
    assert [(issue.code, issue.node_id, issue.blocking) for issue in result.issues] == [
        ("legacy_characteristics_missing", "sf1", True),
    ]


_MISSING = object()


@pytest.mark.parametrize(
    ("characteristics", "expects_legacy_issue"),
    [(_MISSING, True), (None, True), ([], False)],
)
def test_missing_or_none_characteristics_are_legacy_but_explicit_empty_is_not(
    product_process_graph,
    characteristics,
    expects_legacy_issue,
):
    graph = deepcopy(product_process_graph)
    if characteristics is _MISSING:
        graph["nodes"][2].pop("characteristics")
    else:
        graph["nodes"][2]["characteristics"] = characteristics
    if characteristics == []:
        graph["nodes"][3]["characteristics"] = []

    result = map_items(graph)

    assert result.items == ()
    if expects_legacy_issue:
        assert [(issue.code, issue.node_id, issue.blocking) for issue in result.issues] == [
            ("legacy_characteristics_missing", "sf1", True),
        ]
    else:
        assert result.issues == ()


@pytest.mark.parametrize(
    ("fmea_type", "step_ids", "code"),
    [
        ("DFMEA", ("s1",), "unsupported_fmea_type"),
        ("PFMEA", (), "empty_step_selection"),
        ("PFMEA", ("not-a-step",), "invalid_step_selection"),
    ],
)
def test_invalid_mapping_scope_returns_only_a_blocking_issue(product_process_graph, fmea_type, step_ids, code):
    result = map_items(product_process_graph, fmea_type=fmea_type, step_ids=step_ids)

    assert result.items == ()
    assert [(issue.code, issue.blocking) for issue in result.issues] == [(code, True)]


def test_wrong_structural_edge_is_rejected_without_mapping_characteristics(product_process_graph):
    graph = deepcopy(product_process_graph)
    graph["edges"][0]["type"] = "FUNCTION_MAPPED_TO"

    result = map_items(graph)

    assert result.items == ()
    assert [(issue.code, issue.node_id, issue.blocking) for issue in result.issues] == [
        ("invalid_characteristic_graph", "", True),
    ]


def test_candidate_key_is_stable_across_name_and_specification_changes(product_process_graph):
    from app.services.cp_characteristic_mapping import candidate_key
    from app.services.fmea_characteristics import source_key

    original = map_items(product_process_graph).items[0]
    graph = deepcopy(product_process_graph)
    graph["nodes"][2]["characteristics"][0].update({"name": "孔距（修订）", "specification": "10.00±0.10 mm"})
    renamed = map_items(graph).items[0]

    assert source_key(original.source_ref) == source_key(renamed.source_ref)
    assert candidate_key("create", original.source_ref, None) == candidate_key("create", renamed.source_ref, None)
    assert candidate_key("update", original.source_ref, ITEM_ID) == candidate_key("update", renamed.source_ref, ITEM_ID)
    assert candidate_key("create", original.source_ref, None) != candidate_key("update", original.source_ref, ITEM_ID)


@pytest.mark.parametrize("specification,unit,expected", [
    ("20±2", "mm/s", "20±2 mm/s"), ("−60±5", "kPa", "−60±5 kPa"),
    ("3±.5", "N", "3±.5 N"), ("≤0.05", "mm", "≤0.05 mm"),
    ("≥95", "%", "≥95 %"), ("20±2 mm/s", "mm/s", "20±2 mm/s"),
    ("3N (模拟)", "N", "3N (模拟)"), ("≥95%", "%", "≥95%"),
    ("无划伤", None, "无划伤"), (None, "N", None), ("", "N", ""),
    ("  ", "N", "  "), ("20", " ", "20"),
])
def test_criteria_projects_explicit_units_once_without_validating_unit_only(product_process_graph, specification, unit, expected):
    char = product_process_graph['nodes'][2]['characteristics'][0]
    char.update(specification=specification, unit=unit)
    result = map_items(product_process_graph)
    item = next(item for item in result.items if str(item.source_ref.characteristic_id) == PRODUCT_IDS[0])
    assert item.fields['specification_tolerance'] == expected
