"""Backend partitions preserve full selection and demand actual completion."""
import copy
import json
import os
from pathlib import Path

import pytest

from tests.ci import backend_shards as shards


def test_whole_modules_and_new_files_are_owned_automatically():
    assert shards.module_shard("tests/services/agent_runtime/test_existing.py") == 0
    assert shards.module_shard("tests/services/agent_runtime/new/test_added.py") == 0
    assert shards.module_shard("tests/new/test_added.py") == 1
    assert shards.module_shard("tests/new/test_added.py") == shards.module_shard("tests/new/test_added.py")


def receipts():
    nodes = [shards.node_key("tests/a.py::test_a"), shards.node_key("tests/b.py::test_b")]
    return [{"layer": "api", "frozen_sha": "a" * 40, "status": "PASSED", "exit_code": 0,
             "selected": 1, "passed": 1, "skipped": 0, "xfailed": 0, "xpassed": 0, "failed": 0, "errors": 0,
             "backend_shard": {"index": i, "full_nodes": nodes, "full_modules": {shards.node_key("tests/a.py"): [nodes[0]], shards.node_key("tests/b.py"): [nodes[1]]}, "selected_nodes": [node],
                               "executed": {node: {"outcome": "passed", "phases": ["call", "setup", "teardown"]}}}}
            for i, node in enumerate(nodes)]


def test_two_actual_completed_partitions_are_required():
    rows = receipts()
    shards.require_backend_shards(rows, "a" * 40, required={rows[0]["backend_shard"]["selected_nodes"][0]})


@pytest.mark.parametrize("fault", ["failed", "cancelled", "skipped", "missing_receipt", "wrong_sha", "missing_execution", "missing_phase", "overlap", "missing_selection", "different_full", "mandatory_skipped", "duplicate_receipt"])
def test_aggregate_rejects_incomplete_backend(fault):
    rows = receipts()
    required = {rows[0]["backend_shard"]["selected_nodes"][0]}
    if fault in ("failed", "cancelled", "skipped"):
        rows[1]["status"] = fault.upper()
    elif fault == "missing_receipt": rows.pop()
    elif fault == "duplicate_receipt": rows.append(copy.deepcopy(rows[0]))
    elif fault == "wrong_sha": rows[1]["frozen_sha"] = "b" * 40
    elif fault == "missing_execution": rows[0]["backend_shard"]["executed"].clear()
    elif fault == "missing_phase": next(iter(rows[0]["backend_shard"]["executed"].values()))["phases"].remove("teardown")
    elif fault == "overlap": rows[1]["backend_shard"]["selected_nodes"] = rows[0]["backend_shard"]["selected_nodes"][:]
    elif fault == "missing_selection": rows[0]["backend_shard"]["selected_nodes"].clear()
    elif fault == "different_full": rows[1]["backend_shard"]["full_nodes"].pop()
    elif fault == "mandatory_skipped":
        next(iter(rows[0]["backend_shard"]["executed"].values()))["outcome"] = "skipped"
        rows[0].update(passed=0, skipped=1)
    with pytest.raises(ValueError): shards.require_backend_shards(rows, "a" * 40, required=required)


def test_success_codes_cannot_replace_missing_mandatory_node():
    with pytest.raises(ValueError):
        shards.require_backend_shards(receipts(), "a" * 40, required={"f" * 64})


def test_real_pytest_partitions_have_exact_node_union_and_execution_receipts(tmp_path):
    from tests.e2e.capa_outcome_runner import run_pytest_layer
    backend = Path(__file__).resolve().parents[2]
    # Both real child invocations collect the same four parametrized nodes.
    # rootdir makes their source locations identical to the production layout.
    modules = []
    for name in ('tests/services/agent_runtime/test_runtime_probe.py', 'tests/test_remainder_probe.py'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('import pytest\n@pytest.mark.parametrize("n", [0, 1])\ndef test_case(n): pass\n'
                        '@pytest.mark.ci_browser\ndef test_other_layer(): pass\n')
        modules.append(str(path))
    rows = []
    for shard in (0, 1):
        artifacts = tmp_path / f'artifacts-{shard}'
        artifacts.mkdir()
        row = run_pytest_layer(layer='api', targets=modules,
            source={'PATH': os.environ['PATH'], 'OPENQMS_CI_SHA': 'a' * 40},
            database_url='postgresql+asyncpg://u:private@127.0.0.1:1/shard_test',
            artifacts=artifacts, pytest_args=['--noconftest', '--rootdir=' + str(tmp_path), '-c', str(backend/'pytest.ini')], backend_shard=shard)
        rows.append(row)
    result = shards.require_backend_shards(rows, 'a' * 40, required=set())
    assert result['selected'] == 4
    assert all(row['deselected'] == 4 for row in rows)  # two markers + the other shard
    assert set(rows[0]['backend_shard']['selected_nodes']).isdisjoint(rows[1]['backend_shard']['selected_nodes'])
    for row in rows:
        assert 'private' not in json.dumps(row['backend_shard'])


def test_aggregate_cli_writes_one_compatible_actual_api_receipt(tmp_path):
    # The ordinary deployment gate consumes one api receipt in its original
    # artifact. Per-shard receipts stay in their own worker artifacts.
    required = sorted(shards.mandatory_nodes())
    rows = receipts()
    for i, row in enumerate(rows):
        selected = sorted(node for j, nodes in enumerate(shards.mandatory_modules().values()) if j % 2 == i for node in nodes)
        row.update(command=['python', 'tests/e2e/capa_outcome_runner.py', 'api', '--backend-shard', str(i)],
                   selected=len(selected), passed=len(selected), deselected=len(required)-len(selected)+89,
                   warnings=0, elapsed_seconds=1.0)
        row['backend_shard'].update(full_nodes=required, full_modules=shards.mandatory_modules(), selected_nodes=selected,
            executed={node: {'outcome': 'passed', 'phases': ['call', 'setup', 'teardown']} for node in selected})
        path = tmp_path / f'shard-{i}'
        path.mkdir()
        (path / 'api-receipt.json').write_text(json.dumps(row))
    output = tmp_path / 'final'
    assert shards.main(['--receipts', str(tmp_path), '--sha', 'a'*40, '--output', str(output)]) == 0
    receipt = json.loads((output/'api-receipt.json').read_text())
    assert receipt['layer'] == 'api' and receipt['status'] == 'PASSED'
    assert receipt['selected'] == len(required) == receipt['passed']
    assert receipt['deselected'] == 89
    assert receipt['command'] and receipt['shard_commands'] == [row['command'] for row in rows]
    assert (output/'backend-shards.log').is_file()


@pytest.mark.parametrize('layer', ['browser', 'r5-api', 'live', 'scanner'])
def test_sharding_cannot_change_other_execution_boundaries(tmp_path, layer):
    from tests.e2e.capa_outcome_runner import run_pytest_layer
    with pytest.raises(ValueError, match='ordinary API'):
        run_pytest_layer(layer=layer, targets=['tests'], source={}, database_url='', artifacts=tmp_path, backend_shard=0)


def test_explicit_shard_cli_requires_the_entire_ordinary_suite():
    from tests.e2e.capa_outcome_runner import main
    for args in (['browser', '--backend-shard', '0', '--pytest-target', 'tests'],
                 ['api', '--backend-shard', '0'],
                 ['api', '--backend-shard', '1', '--pytest-target', 'tests/capa']):
        with pytest.raises(ValueError, match='api --pytest-target tests'):
            main(args)


def test_collection_only_manifest_cannot_pass_as_execution(tmp_path):
    rows = receipts()
    for row in rows: row['backend_shard']['executed'] = {}
    with pytest.raises(ValueError, match='actually executed'):
        shards.require_backend_shards(rows, 'a' * 40, required=set())


def test_optional_setup_skip_and_xfail_keep_original_ordinary_lane_semantics():
    rows = receipts()
    row = rows[0]
    result = next(iter(row['backend_shard']['executed'].values()))
    for outcome in ('skipped', 'xfailed'):
        row.update(passed=0, skipped=int(outcome == 'skipped'), xfailed=int(outcome == 'xfailed'))
        result.update(outcome=outcome, phases=['setup', 'teardown'])
        shards.require_backend_shards(rows, 'a'*40, required=set())


@pytest.mark.parametrize('fault', ['extra', 'replacement'])
def test_fixed_mandatory_modules_reject_extra_or_replaced_nodes(fault):
    required = sorted(shards.mandatory_nodes())
    rows = receipts()
    modules = {}
    from tests.e2e.capa_outcome_runner import SDK_PROCESS_TARGET, SDK_PROCESS_NAMES, D4_TEXT_PROCESS_TARGET, D4_TEXT_PROCESS_NAMES
    from tests.ci.r5_required import R5_REQUIRED
    for module, names in [(SDK_PROCESS_TARGET, SDK_PROCESS_NAMES), (D4_TEXT_PROCESS_TARGET, D4_TEXT_PROCESS_NAMES),
                         *((name.replace('.', '/') + '.py', names) for name, names in R5_REQUIRED['api'].items())]:
        modules[shards.node_key(module)] = sorted(shards.node_key(module+'::'+name) for name in names)
    extra = shards.node_key(SDK_PROCESS_TARGET+'::test_unregistered_extra')
    modules[shards.node_key(SDK_PROCESS_TARGET)].append(extra)
    if fault == 'replacement':
        removed = modules[shards.node_key(SDK_PROCESS_TARGET)].pop(0)
        required.remove(removed)
    full = sorted(required+[extra])
    for i, row in enumerate(rows):
        selected = full[i::2]
        row.update(selected=len(selected), passed=len(selected))
        row['backend_shard'].update(full_nodes=full, full_modules=modules, selected_nodes=selected,
            executed={node: {'outcome':'passed','phases':['call','setup','teardown']} for node in selected})
    with pytest.raises(ValueError, match='mandatory'):
        shards.require_backend_shards(rows, 'a'*40)


@pytest.mark.parametrize('kind', ['sdk', 'd4', 'r5'])
@pytest.mark.parametrize('fault', ['none', 'missing', 'skip'])
def test_owning_shard_keeps_exact_mandatory_runner_checks(tmp_path, monkeypatch, kind, fault):
    from xml.etree import ElementTree as ET
    from tests.ci.gate_results import COUNTS
    from tests.e2e import capa_outcome_runner as runner

    required = {
        'sdk': (runner.SDK_PROCESS_TARGET, runner.SDK_PROCESS_NAMES),
        'd4': (runner.D4_TEXT_PROCESS_TARGET, runner.D4_TEXT_PROCESS_NAMES),
        'r5': next((name.replace('.', '/') + '.py', names) for name, names in runner.R5_REQUIRED['api'].items()),
    }
    target, names = required[kind]
    owner = shards.module_shard(target)
    names = sorted(names)
    if fault == 'missing':
        names.pop()
    suite = ET.Element('testsuite')
    for name in names:
        ET.SubElement(suite, 'testcase', classname=target[:-3].replace('/', '.'), name=name)
    summary = dict.fromkeys(COUNTS, 0)
    summary.update(selected=len(names), passed=len(names))
    if fault == 'skip':
        ET.SubElement(suite[0], 'skipped', type='pytest.skip')
        summary.update(passed=len(names) - 1, skipped=1)

    class Child:
        stdout = ()
        def __init__(self, command, **kwargs):
            junit = next(argument.split('=', 1)[1] for argument in command if argument.startswith('--junitxml='))
            ET.ElementTree(suite).write(junit)
            Path(kwargs['env']['OPENQMS_GATE_HOOKS']).write_text(json.dumps(summary))
            # This probe checks the runner's mandatory JUnit checks. The separate
            # aggregate tests reject incomplete/forged execution manifests.
            Path(kwargs['env']['OPENQMS_BACKEND_SHARD_EVIDENCE']).write_text(json.dumps({
                'index': owner, 'selected_nodes': names,
            }))
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def wait(self): return 0

    monkeypatch.setattr(runner.subprocess, 'Popen', Child)
    row = runner.run_pytest_layer(layer='api', targets=[target], source={},
        database_url='postgresql+asyncpg://ci:ci@127.0.0.1:1/ci_test', artifacts=tmp_path,
        backend_shard=owner)
    assert row['status'] == ('PASSED' if fault == 'none' else 'FAILED')


def test_collection_proof_uses_the_same_ignores_as_the_actual_make_entry():
    import re
    from tests.e2e.capa_outcome_runner import BACKEND_IGNORES
    makefile = (Path(__file__).resolve().parents[3] / 'Makefile').read_text()
    line = next(line for line in makefile.splitlines() if line.startswith('PYTEST_IGNORES :='))
    assert tuple(re.findall(r'--pytest-arg=--ignore=([^ ]+)', line)) == BACKEND_IGNORES
