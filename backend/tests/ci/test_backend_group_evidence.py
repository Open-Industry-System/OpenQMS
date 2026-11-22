"""Reject incomplete execution even when pytest exits successfully."""
from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from tests.ci.backend_groups import (
    BASIC, GROUPS, group_names, main, pytest_targets, require_group_execution, resolve_targets, verify_receipt,
)
from tests.ci.gate_results import COUNTS

BACKEND = Path(__file__).resolve().parents[2]
SHA = 'a' * 40


@pytest.fixture
def group_run():
    groups = resolve_targets(BACKEND, group_names('basic,msa'))
    nodes = [*BASIC, 'tests/test_msa_service.py::test_msa_service_integration']
    evidence = {
        'collected_files': sorted({node.split('::', 1)[0] for node in nodes}),
        'expected': nodes.copy(),
        'selected': nodes,
        'executed': {node: {'outcome': 'passed', 'phases': ['setup', 'call', 'teardown']}
                     for node in nodes},
    }
    summary = dict.fromkeys(COUNTS, 0) | {'selected': len(nodes), 'passed': len(nodes)}
    return groups, evidence, summary


def test_all_selected_groups_complete(group_run, tmp_path):
    groups, evidence, summary = group_run
    path = tmp_path / 'hook.json'
    path.write_text(json.dumps({'routed': evidence}))
    counts, digest = require_group_execution(groups, path, summary)
    assert counts == {'basic': len(BASIC), 'msa': 1}
    assert re.fullmatch(r'[0-9a-f]{64}', digest)


@pytest.mark.parametrize('defect, diagnostic', [
    ('missing-module', 'collection differs'),
    ('missing-node', 'did not complete every selected node'),
    ('deselected-node', 'omitted a node belonging to the API layer'),
    ('wrong-node', 'did not complete every selected node'),
    ('no-teardown', 'did not complete or legitimately skip'),
    ('wrong-count', 'outcomes disagree'),
    ('basic-skipped', 'mandatory basic backend tests did not pass'),
    ('group-skipped', 'backend group did not pass'),
])
def test_no_green_result_for_incomplete_group(group_run, tmp_path, defect, diagnostic):
    groups, evidence, summary = group_run
    last = evidence['selected'][-1]
    if defect == 'missing-module':
        evidence['collected_files'].remove('tests/test_msa_service.py')
    elif defect == 'missing-node':
        evidence['executed'].pop(last)
    elif defect == 'deselected-node':
        evidence['selected'].remove(last)
        evidence['executed'].pop(last)
        summary['selected'] -= 1
        summary['passed'] -= 1
    elif defect == 'wrong-node':
        evidence['executed'][last + '_unexpected'] = evidence['executed'].pop(last)
    elif defect == 'no-teardown':
        evidence['executed'][last]['phases'].remove('teardown')
    elif defect == 'wrong-count':
        summary['passed'] -= 1
    else:
        skipped = BASIC[0] if defect == 'basic-skipped' else last
        evidence['executed'][skipped] = {'outcome': 'skipped', 'phases': ['setup', 'teardown']}
        summary['passed'] -= 1
        summary['skipped'] += 1
    path = tmp_path / 'hook.json'
    path.write_text(json.dumps({'routed': evidence}))
    with pytest.raises(ValueError, match=diagnostic):
        require_group_execution(groups, path, summary)


@pytest.mark.parametrize('defect', [
    None, 'missing', 'duplicate', 'wrong_sha', 'failed', 'cancelled', 'partial_groups', 'wrong_command', 'missing_digest',
])
def test_final_worker_receipt_binds_selection_and_sha(group_run, monkeypatch, defect):
    groups, _, summary = group_run
    monkeypatch.chdir(BACKEND)
    receipt = summary | {
        'layer': 'api', 'status': 'PASSED', 'exit_code': 0, 'frozen_sha': SHA,
        'command': ['python', *pytest_targets(groups)], 'backend_groups': {'basic': len(BASIC), 'msa': 1},
        'backend_selection_sha256': 'f' * 64,
    }
    if defect == 'wrong_sha':
        receipt['frozen_sha'] = 'b' * 40
    elif defect in {'failed', 'cancelled'}:
        receipt['status'] = defect.upper()
    elif defect == 'partial_groups':
        del receipt['backend_groups']['msa']
    elif defect == 'wrong_command':
        receipt['command'].remove('tests/test_msa_service.py')
    elif defect == 'missing_digest':
        del receipt['backend_selection_sha256']
    receipts = [] if defect == 'missing' else [receipt] * (2 if defect == 'duplicate' else 1)
    if defect is None:
        verify_receipt(receipts, 'basic,msa', SHA)
    else:
        with pytest.raises(ValueError):
            verify_receipt(receipts, 'basic,msa', SHA)


def test_every_route_resolves_and_capable_bundles_include_mandatory_process_and_race_modules():
    groups = resolve_targets(BACKEND, ['basic', *sorted(GROUPS)])
    assert 'tests/e2e/test_agent_sdk_process.py' in groups['receiver']
    assert 'tests/e2e/test_d4_text_local_process.py' in groups['receiver']
    assert 'tests/services/agent_runtime/test_d4_stop_final_fence.py' in groups['capa']
    assert 'tests/services/agent_runtime/test_d4_stop_final_fence.py' in groups['runtime']
    assert 'tests/migrations/test_d4_recovery_delta.py' in groups['tenant']
    assert 'tests/migrations/test_r5_d5_delta.py' in groups['tenant']
    assert {
        'tests/test_characteristic_contract.py', 'tests/test_candidate_scope_stale_updates.py',
        'tests/test_recommended_action_status.py', 'tests/test_security_scope.py',
    } <= set(groups['fmea'])
    targets = pytest_targets(groups)
    # Whole feature modules must subsume shared basic cases without double runs.
    assert 'tests/capa/test_capa_reviewed_writes.py' in targets
    assert not any(node.startswith('tests/capa/test_capa_reviewed_writes.py::') for node in targets)


@pytest.mark.parametrize('layout', ['selected', 'missing', 'duplicate', 'wrong-worker'])
def test_verified_receipt_is_published_only_from_selected_worker(group_run, monkeypatch, tmp_path, layout):
    groups, _, summary = group_run
    monkeypatch.chdir(BACKEND)
    receipt = summary | {
        'layer': 'api', 'status': 'PASSED', 'exit_code': 0, 'frozen_sha': SHA,
        'command': ['python', *pytest_targets(groups)], 'backend_groups': {'basic': len(BASIC), 'msa': 1},
        'backend_selection_sha256': 'f' * 64,
    }
    receipts = tmp_path / 'receipts'
    worker = receipts / f'backend-shard-{"runtime" if layout == "wrong-worker" else "selected"}-evidence'
    worker.mkdir(parents=True)
    if layout != 'missing':
        (worker / 'api-actual-receipt.json').write_text(json.dumps(receipt))
    if layout == 'duplicate':
        (worker / 'api-duplicate-receipt.json').write_text(json.dumps(receipt))
    output = tmp_path / 'output'
    result = main(['basic,msa', '--receipts', str(receipts), '--sha', SHA, '--output', str(output)])
    if layout == 'selected':
        assert result == 0
        assert json.loads((output / 'api-receipt.json').read_text()) == receipt
    else:
        assert result == 1
        assert not output.exists()
