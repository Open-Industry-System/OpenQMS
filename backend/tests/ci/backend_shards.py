"""Two whole-module partitions and strict verification of actual backend execution.

Receipts contain SHA-256 node identities so parameter values never become public
artifacts. Collection supplies the full marker-selected manifest before sharding;
setup/call/teardown reports independently supply completion evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys

RUNTIME_PREFIX = "tests/services/agent_runtime/"
# Whole-module placement balances the measured fixture improvement against the
# same-main historical module timings; new modules still use the prefix fallback.
RUNTIME_MODULES: frozenset[str] = frozenset({
    "tests/api/test_d4_recovery_checkpoint.py",
    "tests/migrations/test_r4b_main_merge_guards.py",
})


def node_key(nodeid: str) -> str:
    return hashlib.sha256(nodeid.encode()).hexdigest()


def module_shard(module: str) -> int:
    """Every current or future module has exactly one whole-file owner."""
    return 0 if module.startswith(RUNTIME_PREFIX) or module in RUNTIME_MODULES else 1


def partition_items(items, rootpath):
    groups = {0: [], 1: []}
    for item in items:
        groups[module_shard(os.path.relpath(item.path, rootpath))].append(item)
    return groups


def mandatory_modules() -> dict[str, list[str]]:
    # Import only constants: no DB, pytest collection or application imports.
    from tests.e2e.capa_outcome_runner import SDK_PROCESS_TARGET, SDK_PROCESS_NAMES, D4_TEXT_PROCESS_TARGET, D4_TEXT_PROCESS_NAMES
    from tests.ci.r5_required import R5_REQUIRED
    modules = [(SDK_PROCESS_TARGET, SDK_PROCESS_NAMES), (D4_TEXT_PROCESS_TARGET, D4_TEXT_PROCESS_NAMES)]
    modules += [(classname.replace(".", "/") + ".py", names) for classname, names in R5_REQUIRED["api"].items()]
    return {node_key(module): sorted(node_key(module + "::" + case) for case in names) for module, names in modules}


def mandatory_nodes() -> set[str]:
    return {node for nodes in mandatory_modules().values() for node in nodes}


def _node_set(values) -> set[str]:
    if not isinstance(values, list) or not values or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in values):
        raise ValueError("invalid or empty node manifest")
    if len(set(values)) != len(values):
        raise ValueError("duplicate nodes")
    return set(values)


def require_backend_shards(receipts: list[dict], sha: str, *, required: set[str] | None = None) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or len(receipts) != 2:
        raise ValueError("exactly two backend execution receipts for one frozen commit are required")
    expected_modules = mandatory_modules() if required is None else {}
    full = None
    full_modules = None
    all_selected: set[str] = set()
    outcomes = {}
    indexes = set()
    for receipt in receipts:
        if receipt.get("layer") != "api" or receipt.get("status") != "PASSED" or receipt.get("exit_code") != 0 or receipt.get("frozen_sha") != sha:
            raise ValueError("backend shard failed, cancelled, skipped or belongs to another commit")
        if any(type(receipt.get(k)) is not int or receipt[k] < 0 for k in ("selected", "passed", "skipped", "xfailed", "xpassed", "failed", "errors")):
            raise ValueError("invalid backend outcome counts")
        if receipt["failed"] or receipt["errors"] or receipt["xpassed"]:
            raise ValueError("backend shard has failed or unexpected outcomes")
        shard = receipt.get("backend_shard", {})
        index = shard.get("index")
        if type(index) is not int or index not in (0, 1) or index in indexes:
            raise ValueError("missing or duplicate backend shard")
        indexes.add(index)
        manifest = _node_set(shard.get("full_nodes"))
        selected = _node_set(shard.get("selected_nodes"))
        modules = shard.get("full_modules")
        if not isinstance(modules, dict) or any(not re.fullmatch(r"[0-9a-f]{64}", module) for module in modules):
            raise ValueError("missing or invalid full module manifest")
        module_nodes = {module: _node_set(nodes) for module, nodes in modules.items()}
        flattened = [node for nodes in module_nodes.values() for node in nodes]
        if len(flattened) != len(set(flattened)) or set(flattened) != manifest:
            raise ValueError("module manifest does not conserve complete selection")
        if any(module_nodes.get(module) != set(nodes) for module, nodes in expected_modules.items()):
            raise ValueError("mandatory module nodes are missing, substituted, extra or duplicated")
        if full_modules is None: full_modules = module_nodes
        if module_nodes != full_modules:
            raise ValueError("full module manifests differ")
        if any(nodes & selected and not nodes <= selected for nodes in module_nodes.values()):
            raise ValueError("module was split between backend workers")
        if full is None: full = manifest
        if manifest != full or selected & all_selected or not selected <= full or receipt["selected"] != len(selected):
            raise ValueError("partition differs from the complete selected manifest")
        executed = shard.get("executed")
        if not isinstance(executed, dict) or set(executed) != selected:
            raise ValueError("collected nodes were not actually executed")
        counts = Counter()
        for node, row in executed.items():
            if not isinstance(row, dict) or row.get("outcome") not in ("passed", "skipped", "xfailed"):
                raise ValueError("invalid execution outcome")
            phases = row.get("phases")
            expected = {"setup", "teardown"} if row["outcome"] in {"skipped", "xfailed"} else {"setup", "call", "teardown"}
            # call-time skips still include call; setup-time skips do not.
            if not isinstance(phases, list) or len(phases) != len(set(phases)) or not expected <= set(phases) <= {"setup", "call", "teardown"}:
                raise ValueError("incomplete execution phases")
            counts[row["outcome"]] += 1
        if any(receipt[k] != counts[k] for k in ("passed", "skipped", "xfailed")):
            raise ValueError("execution evidence and receipt counts differ")
        all_selected.update(selected)
        outcomes.update({node: row["outcome"] for node, row in executed.items()})
    if all_selected != full:
        raise ValueError("shard union does not cover the original full selection")
    required = mandatory_nodes() if required is None else required
    if not required <= all_selected or any(outcomes.get(node) != "passed" for node in required):
        raise ValueError("mandatory backend nodes did not all execute successfully")
    return {"frozen_sha": sha, "status": "PASSED", "selected": len(all_selected), "shards": sorted(indexes)}


# This plugin is loaded only by the explicit backend-shard runner option.
_STATE = {}


def _identity(path, nodeid, rootpath):
    return os.path.relpath(path, rootpath) + "::" + nodeid.partition("::")[2]


def pytest_collection_modifyitems(session, config, items):
    index = int(os.environ["OPENQMS_BACKEND_SHARD"])
    if index not in (0, 1):
        raise ValueError("invalid backend shard")
    _STATE.clear()
    full = [node_key(_identity(item.path, item.nodeid, config.rootpath)) for item in items]
    groups = partition_items(items, config.rootpath)
    selected, removed = groups[index], groups[1 - index]
    selected_keys = []
    full_modules = {}
    for item in items:
        module = os.path.relpath(item.path, config.rootpath)
        full_modules.setdefault(node_key(module), []).append(node_key(_identity(item.path, item.nodeid, config.rootpath)))
        if module_shard(module) == index:
            selected_keys.append(node_key(_identity(item.path, item.nodeid, config.rootpath)))
    if len(set(full)) != len(full):
        raise ValueError("duplicate full-suite node identities")
    _STATE.update(index=index, full_nodes=sorted(full), full_modules={module: sorted(nodes) for module, nodes in full_modules.items()},
                  selected_nodes=sorted(selected_keys), executed={})
    # Shard deselection is deliberately separate from marker/ignore selection.
    # The complete manifest above has already had those original rules applied.
    items[:] = selected
    config.hook.pytest_deselected(items=removed)


pytest_collection_modifyitems.pytest_impl = {"trylast": True}


def pytest_runtest_logreport(report):
    key = node_key(report.location[0] + "::" + report.nodeid.partition("::")[2])
    if key not in _STATE.get("selected_nodes", []):
        raise ValueError("execution outside selected backend shard")
    row = _STATE["executed"].setdefault(key, {"phases": [], "outcome": "incomplete"})
    row["phases"].append(report.when)
    if report.failed:
        row["outcome"] = "failed"
    elif report.when == "call" or (report.when == "setup" and report.skipped):
        row["outcome"] = ("xfailed" if report.skipped else "xpassed") if getattr(report, "wasxfail", None) else report.outcome


def pytest_sessionfinish(session, exitstatus):
    destination = os.environ.get("OPENQMS_BACKEND_SHARD_EVIDENCE")
    if destination:
        output = dict(_STATE)
        for row in output.get("executed", {}).values():
            row["phases"].sort()
        Path(destination).write_text(json.dumps(output, sort_keys=True) + "\n")
        Path(destination).chmod(0o600)


def collect_partition(argv):
    parser = argparse.ArgumentParser(description="Prove the original real pytest collection is partitioned exactly once")
    parser.add_argument("--output", required=True, type=Path, help="private real-node-ID proof (not an upload artifact)")
    args = parser.parse_args(argv)
    from tests.ci.python_isolation import bootstrap
    bootstrap()
    import pytest
    from tests.e2e.capa_outcome_runner import BACKEND_DIR, BACKEND_IGNORES, build_pytest_command

    class CollectionProof:
        def pytest_collection_finish(self, session):
            original = [item.nodeid for item in session.items]
            groups = partition_items(session.items, session.config.rootpath)
            selected = {str(index): [item.nodeid for item in items] for index, items in groups.items()}
            full, left, right = set(original), set(selected["0"]), set(selected["1"])
            if len(full) != len(original) or full != left | right or left & right or not left or not right:
                raise ValueError("real pytest collection is not an exact disjoint partition")
            identities = {node_key(_identity(item.path, item.nodeid, session.config.rootpath)) for item in session.items}
            if not mandatory_nodes() <= identities:
                raise ValueError("full collection is missing mandatory backend nodes")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"original": original, "shards": selected}, sort_keys=True) + "\n")
            args.output.chmod(0o600)
            print("BACKEND_PARTITION_PROOF " + json.dumps({"original": len(full), "runtime": len(left),
                  "remainder": len(right), "intersection": len(left & right), "union": len(left | right)}, sort_keys=True))

    command = build_pytest_command("api", ("tests",), args.output.with_suffix(".xml"),
                                  args.output.with_suffix(".hooks.json"),
                                  pytest_args=["--collect-only", *("--ignore=" + name for name in BACKEND_IGNORES)])
    return int(pytest.main(command[3:], plugins=[CollectionProof()]))


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "collect":
        return collect_partition(arguments[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        paths = sorted(args.receipts.rglob("*-receipt.json"))
        rows = [json.loads(path.read_text()) for path in paths]
        # SDK build subdirectories contain their own receipts; only API receipts
        # are the execution contract of these two backend workers.
        rows = sorted([row for row in rows if row.get("layer") == "api"], key=lambda row: row.get("backend_shard", {}).get("index", -1))
        result = require_backend_shards(rows, args.sha)
        full_count = result["selected"]
        marker_counts = [row.get("deselected", -1) - (full_count - row["selected"]) for row in rows]
        if marker_counts[0] < 0 or marker_counts[0] != marker_counts[1]:
            raise ValueError("shards do not have identical original marker selection")
        if any(not isinstance(row.get("command"), list) or not row["command"] for row in rows):
            raise ValueError("shard receipt lacks the actual executed command")
        result.update(layer="api", exit_code=0, command=[sys.executable, "-m", "tests.ci.backend_shards", *(argv if argv is not None else sys.argv[1:])],
                      shard_commands=[row["command"] for row in rows], deselected=marker_counts[0],
                      **{key: sum(row.get(key, 0) for row in rows) for key in
                         ("passed", "failed", "errors", "skipped", "xfailed", "xpassed", "warnings", "elapsed_seconds")})
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "api-receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        (args.output / "backend-shards.log").write_text("Verified both actual execution manifests, their disjoint union and fixed mandatory nodes.\n" + json.dumps(result, sort_keys=True) + "\n")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("backend shard verification failed: " + str(exc))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
