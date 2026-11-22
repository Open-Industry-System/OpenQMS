"""Resolve a routed API run and verify its evidence before the CI job succeeds."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

from tests.ci.gate_results import COUNTS

# Each basic check must actually pass, including on a preview-only docs run.
BASIC = (
    'tests/test_login_audit_log.py::test_login_success_writes_log',
    'tests/test_login_audit_log.py::test_login_failure_writes_log',
    'tests/test_multitenancy/test_isolation.py::test_tenant_data_isolation',
    'tests/api/test_d4_recovery_checkpoint.py::test_checkpoint_ids_do_not_cross_tenants',
    'tests/capa/test_capa_reviewed_writes.py::test_closure_supplement_and_early_core_http_remain_writable',
    'tests/capa/test_capa_reviewed_writes.py::test_adoption_real_rollback_recovers_with_same_session_user[existing]',
)
GROUPS = {
    'receiver': (
        'tests/cli/test_*.py',
        'tests/e2e/test_agent_*process.py',
        'tests/e2e/test_agent_local_trial_browser.py',
        'tests/e2e/test_agent_task_attachment_browser.py',
        'tests/e2e/test_readonly_agent_process.py',
        'tests/e2e/test_d4_*.py',
        'tests/e2e/test_r5_*.py',
    ),
    'runtime': (
        'tests/api/**/test_*.py',
        'tests/services/agent/**/test_*.py',
        'tests/services/agent_runtime/**/test_*.py',
        'tests/test_agent_review_skill*.py',
        'tests/test_adoption_audit.py',
        'tests/test_llm_provider.py',
    ),
    'capa': (
        'tests/capa/test_*.py',
        'tests/services/test_capa_*.py',
        'tests/services/test_knowledge_entry_source.py',
        'tests/test_capa*.py',
        'tests/test_d7_*.py',
        'tests/test_eightd_state.py',
        'tests/test_adoption_audit.py',
        'tests/api/test_d4_*.py',
        'tests/api/test_readonly_outputs.py',
        'tests/services/agent_runtime/test_d4_*.py',
        'tests/services/agent_runtime/test_d5_*.py',
        'tests/services/agent_runtime/test_readonly_*.py',
        'tests/recommendation/test_*.py',
        'tests/recommendations/test_*.py',
    ),
    'tenant': ('tests/migrations/test_*.py', 'tests/test_multitenancy/test_*.py', 'tests/test_migration*.py'),
    'iqc': (
        'tests/test_iqc*.py', 'tests/capa/test_capa_scar_trigger.py',
        'tests/test_supplier_risk_integration.py', 'tests/test_supply_chain_risk_e2e.py',
    ),
    'fmea': (
        'tests/fmea/test_*.py',
        'tests/test_fmea*.py',
        'tests/test_dfmea*.py',
        'tests/test_pfmea*.py',
        'tests/test_delete_fmea_embeddings.py',
        'tests/test_graph_api.py',
        'tests/test_graph_repository*.py',
        'tests/test_characteristic_consumers.py',
        'tests/test_characteristic_contract.py',
        'tests/test_candidate_scope_stale_updates.py',
        'tests/test_recommended_action_status.py',
        'tests/test_security_scope.py',
        'tests/test_collaboration.py',
        'tests/test_collaboration_api_scope.py',
    ),
    'msa': ('tests/test_msa_service.py',),
    'spc': ('tests/test_spc*.py', 'tests/test_customer_quality.py', 'tests/test_quality_trend*.py'),
    'apqp': ('tests/test_apqp_service.py',),
    'ppap': ('tests/test_ppap_service.py',),
    'control_plan': (
        'tests/test_control_plan*.py', 'tests/test_cp_*.py', 'tests/test_characteristic_consumers.py',
        'tests/test_transition_cp_outbox.py', 'tests/capa/test_capa_doc_gate*.py',
        'tests/test_candidate_scope_stale_updates.py', 'tests/test_security_scope.py',
    ),
    'integrations': (
        'tests/test_erp.py', 'tests/test_mes*.py', 'tests/test_plm*.py', 'tests/test_connector_security.py',
        'tests/test_security_scope_db.py',
    ),
}


def group_names(value: str) -> list[str]:
    names = value.split(',')
    if names != ['basic', *sorted(set(names) - {'basic'})] or not set(names[1:]) <= GROUPS.keys():
        raise ValueError('backend routing needs basic followed by unique known groups in order')
    return names


def resolve_targets(root: Path, names: list[str]) -> dict[str, tuple[str, ...]]:
    targets = {'basic': BASIC}
    for name in names[1:]:
        files = {path.relative_to(root).as_posix() for glob in GROUPS[name] for path in root.glob(glob)}
        if not files:
            raise ValueError(f'backend group selected no modules: {name}')
        targets[name] = tuple(sorted(files))
    return targets


def pytest_targets(groups: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    whole_files = {item for targets in groups.values() for item in targets if '::' not in item}
    # Explicit test IDs in basic can overlap a whole selected module.
    basic_nodes = tuple(item for item in BASIC if item.split('::')[0] not in whole_files)
    return (*basic_nodes, *sorted(whole_files))


def require_group_execution(
    groups: dict[str, tuple[str, ...]], hooks: Path, summary: dict[str, int],
) -> tuple[dict[str, int], str]:
    """Check source files, marker-selected identities, and completed reports."""
    try:
        evidence = json.loads(hooks.read_text())['routed']
        collected = set(evidence['collected_files'])
        expected = evidence['expected']
        selected = evidence['selected']
        executed = evidence['executed']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError('routed backend run has no execution manifest') from exc

    required_files = {target.split('::', 1)[0] for target in pytest_targets(groups)}
    if required_files != collected:
        raise ValueError(f'routed backend collection differs from expected modules: {sorted(required_files ^ collected)}')
    if len(selected) != len(expected) or set(selected) != set(expected):
        raise ValueError('routed collection omitted a node belonging to the API layer')
    if (len(selected) != summary['selected'] or len(set(selected)) != len(selected)
            or set(selected) != executed.keys()):
        raise ValueError('routed backend did not complete every selected node exactly once')

    outcomes = Counter()
    passed = set()
    for identity, row in executed.items():
        outcome, phases = row.get('outcome'), row['phases']
        complete = phases == ['setup', 'call', 'teardown']
        setup_skip = outcome in {'skipped', 'xfailed'} and phases == ['setup', 'teardown']
        if outcome not in {'passed', 'skipped', 'xfailed'} or not (complete or setup_skip):
            raise ValueError('routed backend node did not complete or legitimately skip')
        outcomes[outcome] += 1
        if outcome == 'passed':
            passed.add(identity)
    if any(outcomes[outcome] != summary[outcome] for outcome in ('passed', 'skipped', 'xfailed')):
        raise ValueError('routed backend outcomes disagree with JUnit and pytest counts')

    basic = set(groups['basic'])
    if missing := basic - passed:
        raise ValueError(f'mandatory basic backend tests did not pass: {sorted(missing)}')
    counts = {'basic': len(basic)}
    passed_files = Counter(node.split('::', 1)[0] for node in passed - basic)
    for name, targets in groups.items():
        if name != 'basic':
            counts[name] = sum(passed_files[file] for file in targets)
            if not counts[name]:
                raise ValueError(f'backend group did not pass any tests: {name}')
    digest = hashlib.sha256(json.dumps(sorted(selected)).encode()).hexdigest()
    return counts, digest


def verify_receipt(receipts: list[dict], expected: str, sha: str) -> None:
    if len(receipts) != 1 or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('expected one backend API receipt and the current SHA')
    receipt, = receipts
    if (receipt.get('layer'), receipt.get('status'), receipt.get('exit_code'),
            receipt.get('frozen_sha')) != ('api', 'PASSED', 0, sha):
        raise ValueError('backend API receipt did not pass on the current SHA')
    if any(type(receipt.get(key)) is not int or receipt[key] < 0 for key in COUNTS):
        raise ValueError('backend API receipt has invalid counts')
    if (receipt['failed'] or receipt['errors'] or not receipt['passed']
            or receipt['selected'] != sum(receipt[key] for key in ('passed', 'skipped', 'xfailed', 'xpassed'))):
        raise ValueError('backend API receipt did not complete all selected tests')
    groups = receipt.get('backend_groups')
    digest = receipt.get('backend_selection_sha256')
    command = receipt.get('command')
    if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
        raise ValueError('backend API receipt has no actual command')
    names = group_names(expected)
    if (not isinstance(groups, dict) or set(names) != groups.keys()
                or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)
                or groups.get('basic') != len(BASIC)
                or any(type(count) is not int or not 0 < count <= receipt['passed'] for count in groups.values())
                or not set(pytest_targets(resolve_targets(Path.cwd(), names))) <= set(command)):
        raise ValueError('backend receipt does not match the selected test groups')
    if 'backend_shard' in receipt:
        raise ValueError('routed backend receipt must be unsharded')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('groups')
    parser.add_argument('--receipts', type=Path, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        paths = sorted(args.receipts.rglob('*-receipt.json'))
        if len(paths) != 1 or paths[0].parent != args.receipts / 'backend-shard-selected-evidence':
            raise ValueError('selected worker must supply its unique API receipt')
        receipt = json.loads(paths[0].read_text())
        verify_receipt([receipt], args.groups, args.sha)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'api-receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print('Selected backend verification failed: ' + str(exc), file=sys.stderr)
        return 1
    print('Verified selected backend groups: ' + args.groups)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
