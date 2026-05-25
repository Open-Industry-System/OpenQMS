"""Diff engine for computing differences between FMEA graph and Control Plan versions."""

from __future__ import annotations

from typing import Any


def diff_fmea_graphs(v1_graph: dict, v2_graph: dict) -> dict:
    """Compare two FMEA graph_data snapshots and return structural + RPN diffs.

    Returns:
        {
            "added_nodes":   list of node dicts,
            "deleted_nodes": list of node dicts,
            "modified_nodes": [
                {
                    "node_id": str,
                    "changes": [{"field": str, "old": ..., "new": ...}, ...],
                    "impact_chain": [list of affected downstream node types]
                                     (populated when RPN fields changed)
                },
                ...
            ],
        }
    """
    v1_nodes = {n["id"]: n for n in v1_graph.get("nodes", []) if "id" in n}
    v2_nodes = {n["id"]: n for n in v2_graph.get("nodes", []) if "id" in n}

    v1_ids = set(v1_nodes)
    v2_ids = set(v2_nodes)

    added_nodes = [v2_nodes[nid] for nid in sorted(v2_ids - v1_ids)]
    deleted_nodes = [v1_nodes[nid] for nid in sorted(v1_ids - v2_ids)]

    # RPN-related fields that signal downstream impact
    rpn_fields = {"severity", "occurrence", "detection"}

    # Build a child map from v2 edges for impact chain traversal
    v2_edges = v2_graph.get("edges", [])
    parent_map: dict[str, list[str]] = {}  # target -> [sources]
    for e in v2_edges:
        tgt = e.get("target")
        src = e.get("source")
        if tgt and src:
            parent_map.setdefault(tgt, []).append(src)

    modified_nodes = []
    for nid in sorted(v1_ids & v2_ids):
        old = v1_nodes[nid]
        new = v2_nodes[nid]
        changes: list[dict[str, Any]] = []

        # Compare all scalar fields present in both nodes
        all_keys = set(old.keys()) | set(new.keys())
        for key in sorted(all_keys - {"id"}):
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val != new_val:
                changes.append({"field": key, "old": old_val, "new": new_val})

        if not changes:
            continue

        # Build impact chain: if RPN fields changed, walk edges to find
        # downstream node types affected by this node.
        impact_chain: list[str] = []
        changed_fields = {c["field"] for c in changes}
        if changed_fields & rpn_fields:
            visited: set[str] = set()
            queue = [nid]
            while queue:
                current = queue.pop(0)
                for child_id in parent_map.get(current, []):
                    if child_id not in visited:
                        visited.add(child_id)
                        child_node = v2_nodes.get(child_id)
                        if child_node and child_node.get("type"):
                            impact_chain.append(child_node["type"])
                        queue.append(child_id)

        modified_nodes.append({
            "node_id": nid,
            "changes": changes,
            "impact_chain": impact_chain,
        })

    return {
        "added_nodes": added_nodes,
        "deleted_nodes": deleted_nodes,
        "modified_nodes": modified_nodes,
    }


def diff_cp_items(v1_items: list[dict], v2_items: list[dict]) -> dict:
    """Compare two control plan items snapshot lists.

    Items are matched by ``item_id``.  Items present in only one side are
    added/deleted.  Items present in both are compared field-by-field.

    Returns:
        {
            "added_items":   [...],
            "deleted_items": [...],
            "modified_items": [
                {"item_id": str, "changes": [{"field": str, "old": ..., "new": ...}]}
            ],
        }
    """
    v1_map = {i["item_id"]: i for i in v1_items if "item_id" in i}
    v2_map = {i["item_id"]: i for i in v2_items if "item_id" in i}

    v1_ids = set(v1_map)
    v2_ids = set(v2_map)

    added_items = [v2_map[iid] for iid in sorted(v2_ids - v1_ids)]
    deleted_items = [v1_map[iid] for iid in sorted(v1_ids - v2_ids)]

    modified_items = []
    for iid in sorted(v1_ids & v2_ids):
        old = v1_map[iid]
        new = v2_map[iid]
        changes: list[dict[str, Any]] = []
        all_keys = set(old.keys()) | set(new.keys())
        for key in sorted(all_keys - {"item_id"}):
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val != new_val:
                changes.append({"field": key, "old": old_val, "new": new_val})
        if changes:
            modified_items.append({"item_id": iid, "changes": changes})

    return {
        "added_items": added_items,
        "deleted_items": deleted_items,
        "modified_items": modified_items,
    }


def diff_cp_headers(v1_header: dict, v2_header: dict) -> list[dict]:
    """Compare two control plan header snapshots field-by-field.

    Returns:
        [{"field": str, "old": ..., "new": ...}, ...]
    """
    diffs: list[dict[str, Any]] = []
    all_keys = set(v1_header.keys()) | set(v2_header.keys())
    for key in sorted(all_keys):
        old_val = v1_header.get(key)
        new_val = v2_header.get(key)
        if old_val != new_val:
            diffs.append({"field": key, "old": old_val, "new": new_val})
    return diffs
