"""Strict fresh-C9 evidence readers; no application, database or provider calls."""
from __future__ import annotations

import ast
from collections import Counter
from contextlib import contextmanager
import hashlib
import hmac
import ipaddress
import os
import subprocess
from datetime import datetime
import json
from pathlib import Path
from types import ModuleType
import inspect
from functools import wraps
from uuid import UUID
from xml.etree import ElementTree

FRESH_KIND = 'r6.c9-fresh-evidence.v1'
EXECUTION_KIND = 'r6.c9-fresh-execution.v1'
READONLY_INTERFACE = 'r6.c9-readonly.v1'
LIVE_CLASS = 'tests.e2e.test_r6_live_chain'
LIVE_TEST = 'test_real_terra_empty_root_through_corrected_local_approval'
ZERO = ('failed', 'errors', 'skipped', 'xfailed', 'xpassed')


def exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('exact typed fresh evidence fields required')
    return value


def read_bytes(ref):
    exact(ref, ('path', 'sha256'))
    if type(ref['path']) is not str or type(ref['sha256']) is not str:
        raise ValueError('typed content-addressed reference required')
    path = Path(ref['path'])
    if not path.is_absolute() or len(ref['sha256']) != 64 or any(c not in '0123456789abcdef' for c in ref['sha256']):
        raise ValueError('absolute exact evidence reference required')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ref['sha256']:
        raise ValueError('fresh evidence bytes changed')
    return data


def strict_json(data):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate evidence key')
            result[key] = value
        return result
    def no_constant(_):
        raise ValueError('non-finite evidence value')
    return json.loads(data, object_pairs_hook=no_duplicates, parse_constant=no_constant)


def load(ref):
    return strict_json(read_bytes(ref))


def identifier(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError('canonical evidence UUID required')
    return value


def passed_one(value):
    if value.get('status') != 'PASSED' or type(value.get('exit_code')) is not int or value['exit_code'] != 0:
        raise ValueError('actual whole successful live command required')
    for name, expected in [('selected', 1), ('passed', 1), *[(name, 0) for name in ZERO]]:
        if type(value.get(name)) is not int or value[name] != expected:
            raise ValueError('one genuinely completed live node required')


def body_rows(chain, table):
    rows = chain['database'][table]
    if type(rows) is not list or any(type(row) is not dict or set(row) != {'body'} for row in rows):
        raise ValueError('captured database rows required')
    return [row['body'] for row in rows]


def validate_chain(chain, d4, d5, prepared, models, review, *, session=None):
    """Genuine fresh C9 requires live cloud provenance plus all material checks."""
    if chain['live_provider'] is not True:
        raise ValueError('controlled model evidence is not genuine cloud C9')
    ids = validate_chain_material(chain, d4, d5, prepared, models, session=session)
    for name in ('d4', 'd5'):
        deployment, enrollment = models[name], prepared[name]
        if (deployment['deployment_id'] != enrollment['model_deployment_id'] or deployment['kind'] != 'cloud'
                or deployment['provider'] != 'openai' or deployment['api_protocol'] != 'responses'
                or deployment['model'] != 'gpt-6.1-terra' or deployment['base_url'] != 'https://api.openai.com/v1'
                or deployment['credential_ref'] != 'r5-env:R5_MODEL_CREDENTIAL_OPENAI_TRIAL'):
            raise ValueError('actual approved immutable cloud model required')
    proposals = d5['proposals']
    exact(review, ('report_id', 'task_id', 'selected_proposal_id', 'reviewed_existing_control', 'reason', 'original_text_hashes'))
    if (review['report_id'] != ids['report_id'] or review['task_id'] != ids['d5_task']
            or review['selected_proposal_id'] != ids['a'] or review['reviewed_existing_control'] is not True
            or type(review['reason']) is not str or not review['reason'].strip()
            or review['original_text_hashes'] != {p['proposal_id']: hashlib.sha256(p['original_text'].encode()).hexdigest() for p in proposals}):
        raise ValueError('actual employee semantic decision required')
    return ids


def validate_chain_material(chain, d4, d5, prepared, models, *, session=None):
    """Pure API/DB material checks; this does not attest a live provider or acceptance."""
    required = {'live_provider', 'report_id', 'd4_task', 'd5_task', 'measure_id', 'a', 'b', 'history',
                'verification', 'withdrawal', 'review', 'manual_d5', 'adoption_loss', 'adoption_replay',
                'database', 'receipts', 'switch', 'browser_model_entries'}
    exact(chain, required)
    if type(chain['live_provider']) is not bool:
        raise ValueError('actual material provider classification must be preserved')
    ids = {name: identifier(chain[name]) for name in ('report_id', 'd4_task', 'd5_task', 'measure_id', 'a', 'b')}
    if len({ids['a'], ids['b']}) != 2 or ids['d4_task'] == ids['d5_task']:
        raise ValueError('distinct actual tasks and proposals required')
    for name, model, profile in [('d4', d4, 'model_d4_candidate_v1'), ('d5', d5, 'model_d5_proposal_r6_v1')]:
        entry = chain['browser_model_entries'][name]
        task = model['task']
        if task['task_id'] != ids[name + '_task'] or task['target_capa_id'] != ids['report_id']:
            raise ValueError('captured task/report mismatch')
        if entry['creation']['task'] != task or entry['creation']['command']['report_id'] != ids['report_id']:
            raise ValueError('normal browser creation mismatch')
        if (entry['launch']['status'] != 200 or entry['completion']['status'] != 'completed'
                or entry['completion']['task_id'] != task['task_id']
                or entry['launch']['body']['task_id'] != task['task_id']):
            raise ValueError('actual completed browser launch required')
        enrollment = prepared[name]
        if enrollment['profile'] != profile or enrollment['policy']['profile'] != profile:
            raise ValueError('approved fixed profile required')
        if task['preferred_installation_id'] != enrollment['installation_id'] or task['model_deployment']['deployment_id'] != enrollment['model_deployment_id']:
            raise ValueError('normal installation/deployment binding mismatch')
        deployment = models[name]
        if deployment['deployment_id'] != enrollment['model_deployment_id']:
            raise ValueError('actual selected deployment differs')
        if not deployment['allowed_addresses'] or deployment['version'] != enrollment['policy']['plugin_version']:
            raise ValueError('qualified deployment addresses/version required')
    proposals = d5['proposals']
    if len(proposals) != 2 or {p['proposal_id'] for p in proposals} != {ids['a'], ids['b']} or any(p['state'] != 'pending' for p in proposals):
        raise ValueError('exact two actual pending proposals required')
    if any(p['task_id'] != ids['d5_task'] for p in proposals):
        raise ValueError('actual pending proposal task/report mismatch')
    checkpoint = d5['checkpoint']['checkpoint_id']
    if chain['browser_model_entries']['d5']['checkpoint']['checkpoint_id'] != checkpoint:
        raise ValueError('same actual checkpoint required')
    exact(models, ('d4', 'd5', 'task_bindings', 'runs'))
    commands = chain['database']['commands']
    if (len(commands) != 2 or len({row['command_id'] for row in commands}) != 2
            or {row['proposal_id'] for row in commands} != {ids['a'], ids['b']}
            or any(row['task_id'] != ids['d5_task'] or row['sequence'] <= chain['database']['checkpoint_watermark'] for row in commands)):
        raise ValueError('exact source-bound post-checkpoint save commands required')
    for table in ('capa_d5_proposals', 'capa_r6_source_origins', 'capa_d4_candidates',
                  'capa_d4_root_cause_source_proofs', 'agent_d4_input_receipts', 'agent_d5_basis_receipts'):
        if any(row['report_id'] != ids['report_id'] for row in body_rows(chain, table)):
            raise ValueError('captured source/proposal report mismatch')
    saved = body_rows(chain, 'capa_d5_proposals')
    if {p['proposal_id']: p['state'] for p in saved} != {ids['a']: 'adopted', ids['b']: 'withdrawn'}:
        raise ValueError('actual adopted/withdrawn database facts required')
    if {p['proposal_id']: p['original_text'] for p in saved} != {p['proposal_id']: p['original_text'] for p in proposals}:
        raise ValueError('immutable actual model proposals changed')
    measures = body_rows(chain, 'capa_d5_measures')
    revisions = chain['database']['correction_revisions']
    if (len(measures) != 1 or measures[0]['measure_id'] != ids['measure_id'] or measures[0]['proposal_id'] != ids['a']
            or len(revisions) != 1 or revisions[0]['measure_id'] != ids['measure_id'] or revisions[0]['revision_no'] != 1
            or chain['history']['corrections'][0]['revision_id'] != revisions[0]['revision_id']):
        raise ValueError('actual single versioned correction required')
    origins = body_rows(chain, 'capa_r6_source_origins')
    if (len(origins) != 3 or {p['projection_id'] for p in origins} != {
            'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1', 'fmea.failure_cause.reference.v1'}):
        raise ValueError('complete three actual source origins required')
    proofs = body_rows(chain, 'capa_d4_root_cause_source_proofs')
    if (len(proofs) != 1 or proofs[0]['status'] != 'active'
            or proofs[0]['verification_id'] != chain['verification']['verification_id']
            or chain['verification']['source_proof_issued'] is not True):
        raise ValueError('actual independent verification and proof required')
    sidecars = chain['database']['complete_root_delivery']
    if not sidecars or any(row['report_id'] != ids['report_id'] or row['revision_id'] != proofs[0]['revision_id'] for row in sidecars):
        raise ValueError('actual complete-source delivery bindings required')
    audit = chain['database']['audit']
    attempts = [row for row in audit if row['action'] == 'MODEL_EGRESS_ATTEMPT']
    completions = [row for row in audit if row['action'] == 'MODEL_EGRESS_COMPLETED']
    by_id = {row['log_id']: row for row in attempts}
    if (not attempts or len(by_id) != len(attempts) or len(completions) != len(attempts)
            or Counter(row['correlation_id'] for row in completions) != Counter(by_id.keys())):
        raise ValueError('actual model request/completion bijection required')
    if {row['changed_fields']['task_id'] for row in attempts} != {ids['d4_task'], ids['d5_task']}:
        raise ValueError('actual model calls for both tasks required')
    audit_keys = ('action', 'changed_fields', 'correlation_id', 'factory_id', 'ip_address', 'log_id',
                  'new_values', 'old_values', 'operated_at', 'operated_by', 'record_id', 'table_name', 'tenant_schema', 'user_agent')
    model_rows = [row for row in audit if row['action'].startswith('MODEL_EGRESS_')]
    if len(model_rows) != len(attempts) + len(completions):
        raise ValueError('unexpected failed or unknown model audit action')
    if len({row['log_id'] for row in model_rows}) != len(model_rows):
        raise ValueError('model audit identifiers must be unique')
    for row in model_rows:
        exact(row, audit_keys)
        identifier(row['log_id'])
        identifier(row['record_id'])
        identifier(row['operated_by'])
        if (row['table_name'] != 'agent_model_deployments' or type(row['operated_at']) is not str
                or any(row[key] is not None for key in ('old_values', 'new_values', 'ip_address', 'user_agent', 'tenant_schema'))
                or (session is not None and (row['operated_by'] != session['actors']['qe']['user_id']
                                            or row['factory_id'] != session['factory_id']))):
            raise ValueError('model audit may contain only exact safe operational metadata')
        timestamp = datetime.fromisoformat(row['operated_at'])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError('model audit timestamp must be an actual timezone-aware timestamp')
    for row in attempts:
        task = row['changed_fields']['task_id']
        name = 'd4' if task == ids['d4_task'] else 'd5'
        fields = ('task_id', 'run_id', 'deployment_id')
        exact(row['changed_fields'], fields if name == 'd4' else (*fields, 'version', 'snapshot_hmac'))
        if (row['record_id'] != models[name]['deployment_id'] or row['changed_fields']['deployment_id'] != row['record_id']
                or (name == 'd4' and row['correlation_id'] is not None)
                or (name == 'd5' and (row['changed_fields']['version'] != models[name]['version']
                    or row['correlation_id'] != row['changed_fields']['run_id']))):
            raise ValueError('actual cloud attempt deployment/run metadata mismatch')
        snapshot = row['changed_fields'].get('snapshot_hmac')
        if snapshot is not None and (type(snapshot) is not str or len(snapshot) != 64 or any(c not in '0123456789abcdef' for c in snapshot)):
            raise ValueError('actual source snapshot signature is malformed')
        runs = [run for run in models['runs'] if run['run_id'] == row['changed_fields']['run_id'] and run['task_id'] == task]
        if len(runs) != 1 or runs[0]['installation_id'] != prepared[name]['installation_id']:
            raise ValueError('actual model attempt run binding mismatch')
    if not any(row['changed_fields'].get('snapshot_hmac') for row in attempts if row['changed_fields']['task_id'] == ids['d5_task']):
        raise ValueError('actual complete-source D5 model delivery audit required')
    for name in ('d4', 'd5'):
        bindings = [binding for binding in models['task_bindings'] if binding['task_id'] == ids[name + '_task']]
        if len(bindings) != 1 or bindings[0]['deployment_id'] != models[name]['deployment_id'] or bindings[0]['config_hmac'] != models[name]['config_hmac']:
            raise ValueError('actual immutable task/model approval binding required')
    for row in completions:
        attempt = by_id[row['correlation_id']]
        fields = ('task_id', 'run_id', 'deployment_id')
        exact(row['changed_fields'], fields if attempt['changed_fields']['task_id'] == ids['d4_task'] else (*fields, 'version'))
        if (row['changed_fields'] != {k: v for k, v in attempt['changed_fields'].items() if k != 'snapshot_hmac'}
                or row['record_id'] != attempt['record_id']):
            raise ValueError('model completion identity mismatch')
    final = chain['review']
    if (final['binding_status'] != 'verified' or final['contract'] != 'capa.outcome-review.v2'
            or {row['measure_id'] for row in final['d5_measures']} != {ids['measure_id']}
            or len(final['local_closure']['propagation']['channels']) != 4
            or set(final['local_closure']['propagation']['channels'].values()) != {'NOT_EXECUTED'}):
        raise ValueError('actual approved local closure required')
    return ids


def validate_fresh_c9(summary, execution_ref, readonly_manifest_ref, snapshot_ref, *, repo=None):
    exact(summary, ('kind', 'status', 'evidence_method', 'report_id', 'execution', 'readonly_final'))
    if (summary['kind'] != FRESH_KIND or summary['status'] != 'PASS'
            or summary['evidence_method'] != 'FRESH_SINGLE_PASS' or summary['execution'] != execution_ref):
        raise ValueError('typed genuine single-PASS C9 required')
    exact(summary['readonly_final'], ('manifest_sha256', 'evidence_sha256'))
    if summary['readonly_final'] != {'manifest_sha256': readonly_manifest_ref['sha256'], 'evidence_sha256': snapshot_ref['sha256']}:
        raise ValueError('same fresh readonly evidence required')
    execution = load(execution_ref)
    refs = ('receipt', 'junit', 'hooks', 'chain', 'attempt', 'source_manifest', 'operator_manifest',
            'configurations', 'resource', 'prepared', 'models', 'employee_review', 'd4_model', 'd5_model', 'accepted_switch',
            'authority', 'build', 'build_config', 'switch_environment', 'switch', 'session', 'policy')
    exact(execution, ('kind', 'execution_id', *refs))
    if execution['kind'] != EXECUTION_KIND:
        raise ValueError('fresh execution version required')
    values = {name: load(execution[name]) for name in refs if name not in ('junit', 'configurations')}
    passed_one(values['receipt'])
    identifier(execution['execution_id'])
    if values['receipt'].get('frozen_sha') != values['source_manifest']['source_revision']:
        raise ValueError('original live receipt must use the final committed source freeze')
    hooks = values['hooks']
    for name, count in [('selected', 1), ('passed', 1), *[(name, 0) for name in ZERO]]:
        if type(hooks.get(name)) is not int or hooks[name] != count:
            raise ValueError('fresh original hook counts required')
    try:
        cases = list(ElementTree.fromstring(read_bytes(execution['junit'])).iter('testcase'))
    except ElementTree.ParseError as error:
        raise ValueError('actual live JUnit is malformed') from error
    if (len(cases) != 1 or cases[0].get('classname') != LIVE_CLASS or cases[0].get('name') != LIVE_TEST
            or any(cases[0].find(name) is not None for name in ('skipped', 'failure', 'error'))):
        raise ValueError('exact genuine whole live JUnit node required')
    properties = cases[0].findall('./properties/property')
    if len(properties) != 1 or properties[0].get('name') != 'r6_live_binding':
        raise ValueError('one actual completed live node binding required')
    binding = strict_json(properties[0].get('value', ''))
    expected_binding = dict(kind='r6.live-test-binding.v1', source_revision=values['source_manifest']['source_revision'],
        execution_id=execution['execution_id'], owner_nonce=values['resource']['owner_nonce'], report_id=values['chain']['report_id'],
        resource=execution['resource'], candidate_configuration=execution['configurations']['candidate'],
        **{key: execution[key] for key in ('chain', 'd4_model', 'd5_model', 'attempt', 'switch')})
    exact(binding, expected_binding.keys())
    if (binding != expected_binding or values['resource'].get('r6_c9_execution_id') != execution['execution_id']
            or values['switch'] != values['chain']['switch']):
        raise ValueError('actual live node owner, source, execution and output refs differ')
    actual_command = values['receipt']['command']
    python = values['source_manifest']['executables']['python']
    if (type(actual_command) is not list or not actual_command or type(actual_command[0]) is not str
            or not Path(actual_command[0]).is_absolute() or Path(actual_command[0]).resolve() != Path(python['path']).resolve()
            or hashlib.sha256(Path(actual_command[0]).read_bytes()).hexdigest() != python['sha256']):
        raise ValueError('actual live interpreter must be the registered Python binary')
    command = [actual_command[0], '-m', 'tests.ci.pytest_bootstrap',
               'tests/e2e/test_r6_live_chain.py', '-m', 'live_provider', '-q', '--tb=short', '-rA',
               '--junitxml=<private>', '-p', 'tests.ci.gate_results', '-o', 'faulthandler_timeout=120']
    if values['receipt']['command'] != command or values['receipt']['layer'] != 'live':
        raise ValueError('exact normal genuine live runner required')
    resource = values['resource']
    if ('r6_controlled_model' in resource or resource['host'] != '127.0.0.1'
            or not resource['test_database'].endswith('_test')):
        raise ValueError('separate genuine owner-bound resource required')
    configurations = exact(execution['configurations'], ('candidate', 'compatible'))
    candidate, compatible = load(configurations['candidate']), load(configurations['compatible'])
    if (candidate.get('R6_GENERATION_ENABLED', 'true') != 'true' or compatible.get('R6_GENERATION_ENABLED') != 'false'
            or {k: v for k, v in candidate.items() if k != 'R6_GENERATION_ENABLED'} != {k: v for k, v in compatible.items() if k != 'R6_GENERATION_ENABLED'}
            or candidate['OPENQMS_TEST_RESOURCE_FILE'] != execution['resource']['path']):
        raise ValueError('exact candidate/compatible owner configurations required')
    validate_provenance(values, candidate, configurations, execution, repo=repo)
    target, session = values['chain']['switch']['target'], values['session']
    if (session['report_id'] != values['chain']['report_id'] or session['tenant_id'] != target['tenant']['tenant_id']
            or session['schema'] != target['tenant']['schema'] or type(session['generation']) is not int
            or session['generation'] != target['tenant']['generation']
            or values['policy'] != values['prepared']['d5']['policy']
            or candidate['AGENT_R5_CONTROLLED_POLICY_FILE'] != execution['policy']['path']):
        raise ValueError('actual constructor session or accepted policy differs')
    enrollments = [entry for entry in values['build_config']['execution']['enrollments'] if entry['profile'] == 'model_d5_proposal_r6_v1']
    if len(enrollments) != 1 or enrollments[0]['policy_sha256'] != execution['policy']['sha256']:
        raise ValueError('registered final profile policy bytes differ')
    ids = validate_chain(values['chain'], values['d4_model'], values['d5_model'], values['prepared'], values['models'], values['employee_review'], session=values['session'])
    if (summary['report_id'] != ids['report_id'] or values['attempt'] != {'stage': 'approved-and-preserved', 'report_id': ids['report_id']}):
        raise ValueError('whole same-report final attempt required')
    switch = values['chain']['switch']
    accepted = values['accepted_switch']['accepted']
    if (execution['accepted_switch'] != switch['exercise_authority_chain'] or accepted['state'] != 'switched'
            or accepted['operation_ref'] != switch['operation'] or accepted['document_digest'] != switch['current_accepted_document_digest']
            or resource['owner_nonce'] != switch['target']['owner']):
        raise ValueError('actual durable same-operation switch required')
    accepted_epoch(switch, values['authority']['record'])
    manifest = exact(load(readonly_manifest_ref), ('kind', 'execution', 'readonly_verifier', 'external_evidence'))
    if (manifest['kind'] != 'r6.c9-readonly-manifest.v1' or manifest['execution'] != execution_ref
            or manifest['external_evidence'].get(execution['receipt']['path']) != execution['receipt']['sha256']):
        raise ValueError('fresh readonly manifest must bind original execution')
    registered_verifier_bytes(values, manifest['readonly_verifier'], repo=repo)
    snapshot = load(snapshot_ref)
    validate_readonly_material(values['chain'], snapshot)
    validate_d4_input_receipts(values, snapshot)
    return values


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_provenance(values, candidate, configurations, execution, *, repo=None):
    """Bind source, SDK, operators, ownership and normal immutable approvals."""
    repo = Path(repo or Path(__file__).resolve().parents[3]).resolve()
    source = exact(values['source_manifest'], ('kind', 'repository_root', 'source_revision', 'files',
                                               'external_files', 'executables', 'packages'))
    if source['kind'] != 'r6.executed-sources.v1' or Path(source['repository_root']).resolve() != repo:
        raise ValueError('complete final repository source manifest required')
    verify_committed_source(repo, source)
    if any(not Path(path).is_absolute() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != value for path, value in source['external_files'].items()):
        raise ValueError('external executed artifact/SDK source changed')
    registry = exact(values['authority'], ('record', 'signature'))
    keys = values['switch_environment']
    if (keys.get('R6_SWITCH_AUTHORITY_KEY') != os.environ.get('R6_SWITCH_AUTHORITY_KEY')
            or candidate.get('OPENQMS_TEST_RESOURCE_FILE') != os.environ.get('OPENQMS_TEST_RESOURCE_FILE')):
        raise ValueError('independently selected owner/authority context required')
    if (not os.environ.get('R6_SWITCH_AUTHORITY_FILE')
            or Path(os.environ['R6_SWITCH_AUTHORITY_FILE']).resolve() != Path(execution['authority']['path']).resolve()
            or hashlib.sha256(Path(os.environ['R6_SWITCH_AUTHORITY_FILE']).read_bytes()).hexdigest() != execution['authority']['sha256']):
        raise ValueError('independently registered authority file required')
    if not hmac.compare_digest(registry['signature'], hmac.new(keys['R6_SWITCH_AUTHORITY_KEY'].encode(), digest(registry['record']).encode(), hashlib.sha256).hexdigest()):
        raise ValueError('authenticated owner authority required')
    record, build, config = registry['record'], values['build'], values['build_config']
    target = values['chain']['switch']['target']
    resource = values['resource']
    if (record['target'] != target or record['resource_record'] != execution['resource']['path']
            or record['config_file'] != execution['build_config']['path'] or target['owner'] != resource['owner_nonce']
            or target['database'] != resource['test_database'] or target['deployment_role'] != 'synthetic_exercise'
            or target['environment'] != 'isolated_exercise' or config['owner'] != resource['owner_nonce']
            or config['tenant'] != target['tenant'] or config['environment_id'] != target['environment_id']):
        raise ValueError('owner/tenant/database/build configuration mismatch')
    if (digest(build) != target['candidate_build'] or target['compatible_build'] != target['candidate_build']
            or execution['build']['sha256'] != record['build_artifacts'][target['candidate_build']]['sha256']
            or execution['build_config']['sha256'] != target['config_digest'] or build['config_digest'] != target['config_digest']
            or not build['source_manifest'] or target['source_manifest'] != digest(build['source_manifest'])
            or build['source_revision'] != source['source_revision'] or Path(build['source_root']).resolve() != repo
            or build['schema_heads'] != [target['public_head'], target['tenant_head']]
            or any(source['files'].get(name) != value for name, value in build['source_manifest'].items())
            or config['execution']['deployment_configurations'] != configurations):
        raise ValueError('final source/build/schema/config identity mismatch')
    required_execution = {'backend/tests/e2e/r6_live_harness.py', 'backend/tests/e2e/r6_exercise.py',
        'backend/tests/e2e/test_r6_live_chain.py', 'backend/tests/e2e/test_r6_entry_switch_browser.py',
        'backend/tests/e2e/test_r6_entry_switch_process.py', 'backend/tests/capa/r6_switch_support.py',
        'backend/tests/capa/r6_support.py', 'frontend/playwright.agent.config.ts',
        'frontend/e2e/specs/capa/r6-entry-switch.spec.ts'}
    if set(config['execution']['execution_artifacts']) != required_execution:
        raise ValueError('complete actual app/browser launcher closure required')
    for name, value in config['execution']['execution_artifacts'].items():
        if source['files'].get(name) != value:
            raise ValueError('actual application/browser execution source omitted')
    for name in ('node', 'chromium'):
        artifact = config['execution'][name]
        ref = source['executables']['browser' if name == 'chromium' else name]
        read_bytes(ref)
        if ref != artifact:
            raise ValueError('actual browser/Node executable mismatch')
    python = source['executables']['python']
    read_bytes(python)
    if python != {'path': build['executable'], 'sha256': build['executable_digest']}:
        raise ValueError('actual Python executable mismatch')
    if set(config['execution']['backend_packages']) != {'openai', 'httpx', 'httpcore'}:
        raise ValueError('complete actually installed backend transport SDKs required')
    for name, value in config['execution']['frontend_dependencies'].items():
        if (source['files'].get(name) or source['external_files'].get(str(repo / name))) != value:
            raise ValueError('actual installed frontend runner bytes omitted')
    for name, package in config['execution']['backend_packages'].items():
        declared = source['packages'][name]
        if declared['version'] != package['version'] or declared['sources'] != package['sources']:
            raise ValueError('actual SDK/package sources mismatch')
        root = Path(declared['root'])
        if not root.is_absolute() or any(source['external_files'].get(str(root / path)) != value for path, value in package['sources'].items()):
            raise ValueError('complete installed SDK/package bytes required')
    operators = exact(values['operator_manifest'], ('kind', 'owner', 'files'))
    if (operators['kind'] != 'r6.c9-operators.v1' or operators['owner'] != resource['owner_nonce']
            or set(operators['files']) != {'prepare.py', 'live.py', 'run.py'}
            or set(operators['files']) != set(config['execution']['operator_adapters'])):
        raise ValueError('registered operator source inventory required')
    directory = Path(execution['resource']['path']).parent.resolve()
    for name, ref in operators['files'].items():
        read_bytes(ref)
        if Path(ref['path']).resolve() != directory / name or ref['sha256'] != config['execution']['operator_adapters'][name]:
            raise ValueError('unknown or altered operator source')
    for name in ('d4', 'd5'):
        policy = values['prepared'][name]['policy']
        model = values['models'][name]
        fingerprint = dict(approval={key: policy[key] for key in ('artifact', 'artifact_sha256', 'interpreter', 'interpreter_sha256', 'launcher_sha256')},
            tenant_id=policy['tenant_id'], tenant_generation=policy['tenant_generation'], installation_id=policy['installation_id'],
            credential_epoch=policy['credential_epoch'], plugin_version=policy['plugin_version'], platform_port=policy['platform_port'],
            expires_at=str(datetime.fromisoformat(policy['expires_at'])), profile=policy['profile'])
        pins = dict(policy_sha256=digest(fingerprint), artifact_sha256=policy['artifact_sha256'],
                    interpreter_sha256=policy['interpreter_sha256'], launcher_sha256=policy['launcher_sha256'], profile=policy['profile'])
        fields = ('deployment_id', 'name', 'version', 'tenant_generation', 'kind', 'provider', 'model', 'base_url',
                  'allowed_addresses', 'credential_ref', 'executor_pins', 'created_by')
        data = {key: model[key] for key in fields}
        data.update(tenant_id=target['tenant']['tenant_id'], api_protocol='responses')
        signature = hmac.new(candidate['SECRET_KEY'].encode(), b'openqms.r5.model-deployment.v1\n' + json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode(), hashlib.sha256).hexdigest()
        if (model['enabled'] is not True or model['tenant_generation'] != target['tenant']['generation']
                or policy['tenant_id'] != target['tenant']['tenant_id'] or policy['tenant_generation'] != target['tenant']['generation']
                or model['executor_pins'] != pins or not hmac.compare_digest(model['config_hmac'], signature)
                or not model['allowed_addresses'] or not all(ipaddress.ip_address(address).is_global for address in model['allowed_addresses'])
                or hashlib.sha256(Path(policy['artifact']).read_bytes()).hexdigest() != policy['artifact_sha256']
                or hashlib.sha256(Path(policy['interpreter']).read_bytes()).hexdigest() != policy['interpreter_sha256']):
            raise ValueError('normal immutable cloud deployment approval/pins differ')


def registered_verifier_bytes(values, verifier_ref, *, repo=None):
    """Resolve code only AFTER the caller authenticates full execution provenance.

    The normal accepted configuration registers prepare.py. Its verified literal
    descriptor registers this fixed reader, so a handoff cannot authorize code.
    This function neither imports nor executes either referenced file.
    """
    repo = Path(repo or Path(__file__).resolve().parents[3]).resolve()
    name = 'backend/tests/e2e/r6_fresh_readonly.py'
    operators = values['operator_manifest']
    if operators['kind'] != 'r6.c9-operators.v1' or operators['owner'] != values['resource']['owner_nonce']:
        raise ValueError('reader operator owner differs')
    prepare = operators['files'].get('prepare.py')
    registered = values['build_config']['execution']['operator_adapters'].get('prepare.py')
    if not prepare or prepare['sha256'] != registered:
        raise ValueError('reader registration operator is unknown')
    tree = ast.parse(read_bytes(prepare), filename=prepare['path'])
    declarations = [node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))
                    and any(isinstance(target, ast.Name) and target.id == 'R6_READONLY_VERIFIER'
                            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]))]
    if len(declarations) != 1 or declarations[0] not in tree.body:
        raise ValueError('one top-level literal reader registration required')
    descriptor = exact(ast.literal_eval(declarations[0].value), ('path', 'sha256', 'interface'))
    if (descriptor['interface'] != READONLY_INTERFACE or Path(descriptor['path']).resolve() != repo / name
            or {key: descriptor[key] for key in ('path', 'sha256')} != verifier_ref
            or values['source_manifest']['files'].get(name) != descriptor['sha256']):
        raise ValueError('unregistered reader path, interface or source')
    return read_bytes(verifier_ref)


def trusted_readonly_verifier(summary, execution_ref, readonly_manifest_ref, snapshot_ref, verifier_ref, *, original=None):
    """Validate all provenance before compiling exactly the registered bytes."""
    values = validate_fresh_c9(summary, execution_ref, readonly_manifest_ref, snapshot_ref)
    if original is None:
        raise ValueError('authenticated original directory is required before reader compile')
    captured = verified_original_files(load(execution_ref), original)
    source = registered_verifier_bytes(values, verifier_ref)
    module = ModuleType('r6_registered_readonly_verifier')
    module.__file__ = verifier_ref['path']
    module._verified_original = captured
    module._verified_facts = values
    # No importlib reread: the compiled bytes are the bytes actually authenticated.
    exec(compile(source, verifier_ref['path'], 'exec'), module.__dict__)
    if (module.INTERFACE != READONLY_INTERFACE or not callable(getattr(module, 'configure', None))
            or not callable(getattr(module, 'ReadOnlyExercise', None))
            or not inspect.iscoroutinefunction(getattr(module, 'verify', None))):
        raise ValueError('registered reader runtime interface differs')
    return module


def accepted_epoch(switch, registry=None):
    """Derive epoch from the hash-bound durable accepted renewal, never a constant."""
    chain = load(switch['exercise_authority_chain'])
    accepted = exact(chain['accepted'], ('state', 'epoch', 'operation_ref', 'document_digest'))
    if (chain['stage'] != 'switched-confirmed' or accepted['state'] != 'switched'
            or type(accepted['epoch']) is not int or type(chain['closed_epoch']) is not int
            or chain['closed_epoch'] < 1 or accepted['epoch'] != chain['closed_epoch'] + 2
            or accepted['operation_ref'] != switch['operation'] or chain['operation_ref'] != switch['operation']
            or accepted['document_digest'] != switch['current_accepted_document_digest']
            or chain['renewed_document']['canonical_digest'] != accepted['document_digest']
            or chain['initial_document']['canonical_digest'] != switch['original_exercise_digest']):
        raise ValueError('same accepted durable switch ledger required')
    from app.services.capa_switch_evidence import Document
    for key in ('initial_document', 'renewed_document'):
        ref = {name: chain[key][name] for name in ('path', 'sha256')}
        document = Document.model_validate(load(ref)).model_dump(mode='json', by_alias=True)
        if (document['target'] != switch['target'] or document['kind'] != 'exercise_input'
                or document['purpose'] != 'r6-rehearsal.v1' or document['exercise_id'] != chain['exercise_id']
                or digest(document) != chain[key]['canonical_digest']
                or (registry is not None and digest(document) not in registry['authorized_documents'])):
            raise ValueError('accepted document authority/target binding differs')
    return accepted['epoch']


def verified_original_files(execution, original):
    """Capture the exact authenticated files used by common app construction.

    Call only after validating fresh execution provenance. A valid proof cannot
    authorize a different directory's environment, registry or constructor data.
    """
    directory = Path(original).resolve()
    if directory != Path(execution['resource']['path']).resolve().parent:
        raise ValueError('original directory is not the trusted resource parent')
    names = {'resource': 'resource.json', 'authority': 'authority.json', 'build': 'build.json',
        'build_config': 'config.json', 'prepared': 'prepared.json', 'switch_environment': 'switch-environment.json',
        'chain': 'c9-evidence.json', 'd4_model': 'd4-model.json', 'd5_model': 'd5-model.json',
        'attempt': 'live-attempt.json', 'switch': 'build-and-switch.json', 'session': 'session.json', 'policy': 'policy.json'}
    refs = {name: execution[key] for key, name in names.items()}
    refs.update({'environment.json': execution['configurations']['candidate'],
                 'environment.compat.json': execution['configurations']['compatible']})
    captured = {}
    for name, ref in refs.items():
        if ref['path'] != str(directory / name) or (directory / name).is_symlink():
            raise ValueError('original fixed-name file is not the authenticated reference')
        captured[name] = strict_json(read_bytes(ref))
    if Path(captured['resource.json']['r6_exercise_directory']).resolve() != directory:
        raise ValueError('constructor exercise directory differs')
    return captured


def verify_committed_source(repo, source):
    """Bind the actual recorded commit, current committed tree and worktree.

    Markdown-only follow-ups preserve exact executed source identities. Code,
    mode, index, symlink and untracked-file drift fail closed.
    """
    revision = source['source_revision']
    if type(revision) is not str or len(revision) not in (40, 64) or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('exact recorded source commit required')
    def git(*args):
        try:
            return subprocess.check_output(['git', *args], cwd=repo, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as error:
            raise ValueError('recorded source Git object is unavailable') from error
    if git('cat-file', '-t', revision).strip() != b'commit':
        raise ValueError('recorded source must be a commit object')
    def tree(commit):
        result = {}
        for row in git('ls-tree', '-r', '--full-tree', '-z', commit).split(b'\0'):
            if not row:
                continue
            metadata, name = row.split(b'\t', 1)
            name = name.decode()
            if name.lower().endswith('.md'):
                continue
            mode, kind, blob = metadata.decode().split()
            if mode not in ('100644', '100755') or kind != 'blob':
                raise ValueError('unsupported non-file or symlink in executed tree')
            result[name] = (mode, blob)
        return result
    recorded = tree(revision)
    if tree('HEAD') != recorded or set(source['files']) != set(recorded):
        raise ValueError('current committed execution tree differs from recorded source')
    index = {}
    for row in git('ls-files', '--stage', '-z').split(b'\0'):
        if not row:
            continue
        metadata, name = row.split(b'\t', 1)
        name = name.decode()
        if name.lower().endswith('.md'):
            continue
        mode, blob, stage = metadata.decode().split()
        if stage != '0':
            raise ValueError('unmerged execution source is not qualified')
        index[name] = (mode, blob)
    untracked = [name for name in git('ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
                 if name and not name.lower().endswith('.md')]
    if index != recorded or untracked:
        raise ValueError('staged or untracked execution source is not qualified')
    for name, (mode, blob) in recorded.items():
        path = repo / name
        if path.is_symlink() or not path.is_file() or bool(path.stat().st_mode & 0o100) != (mode == '100755'):
            raise ValueError('executed file type or mode changed')
        data = path.read_bytes()
        algorithm = hashlib.sha1 if len(blob) == 40 else hashlib.sha256
        actual_blob = algorithm(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if hashlib.sha256(data).hexdigest() != source['files'][name] or actual_blob != blob:
            raise ValueError('executed bytes differ from recorded Git blob')


def validate_d4_input_receipts(values, snapshot):
    """Associate actual delivered input receipts with the signed model and source set."""
    chain, models, session = values['chain'], values['models'], values['session']
    task_id = chain['d4_task']
    enrollment = values['prepared']['d4']
    tasks = [task for task in snapshot['immutable_original_model']['agent_tasks'] if task['task_id'] == task_id]
    if len(tasks) != 1 or tasks[0]['executor_user_id'] != session['actors']['qe']['user_id']:
        raise ValueError('actual D4 executor task binding differs')
    fields = ('kind', 'projection_id', 'version', 'source_version_counter', 'snapshot_id',
              'fmea_id', 'node_id', 'factory_id', 'product_line_code')
    origins = body_rows(chain, 'capa_r6_source_origins')
    versions = {row['source_id']: {key: row[key] for key in fields} for row in origins}
    receipts = body_rows(chain, 'agent_d4_input_receipts')
    if not receipts or len({identifier(row['receipt_id']) for row in receipts}) != len(receipts):
        raise ValueError('actual unique delivered D4 input receipts required')
    for row in receipts:
        runs = [run for run in models['runs'] if run['run_id'] == row['run_id'] and run['task_id'] == task_id
                and run['installation_id'] == enrollment['installation_id']]
        if (row['report_id'] != chain['report_id'] or row['task_id'] != task_id or len(runs) != 1
                or row['installation_id'] != enrollment['installation_id']
                or row['deployment_id'] != models['d4']['deployment_id']
                or row['deployment_config_hmac'] != models['d4']['config_hmac']
                or row['executor_id'] != session['actors']['qe']['user_id']
                or type(row['tenant_generation']) is not int or row['tenant_generation'] != session['generation']
                or type(row['lease_epoch']) is not int or row['lease_epoch'] < 0 or row['lease_epoch'] > runs[0]['lease_epoch']
                or type(row['source_count']) is not int or row['source_count'] != 3 or len(versions) != 3
                or row['input_versions'] != versions):
            raise ValueError('D4 input receipt task/run/recipient/authority/source binding differs')


@contextmanager
def checker_environment(independent_caller):
    """Use only the pre-proof caller anchor, restoring even exceptional exits."""
    runtime = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(independent_caller)
        yield
    finally:
        os.environ.clear()
        os.environ.update(runtime)


def validate_readonly_material(chain, snapshot):
    """Exact endpoint projection and persisted-state parity; never live acceptance."""
    verification = dict(chain['verification'])
    if verification.pop('source_proof_issued') is not True:
        raise ValueError('actual independent source proof issuance required')
    proof, = body_rows(chain, 'capa_d4_root_cause_source_proofs')
    identifier(proof['proof_id'])
    if proof['verification_id'] != verification['verification_id'] or proof['status'] != 'active':
        raise ValueError('actual verification/source-proof UUID binding differs')
    if (snapshot['report_id'] != chain['report_id'] or snapshot['measure_id'] != chain['measure_id']
            or snapshot['a'] != chain['a'] or snapshot['b'] != chain['b'] or snapshot['current']['status'] != 'D8_CLOSURE'
            or snapshot['original_switch'] != chain['switch'] or snapshot['history'] != chain['history']
            or snapshot['review'] != chain['review'] or snapshot['verification'] != [verification]
            or digest({k: sorted(v, key=digest) if isinstance(v, list) else v for k, v in snapshot['database'].items()})
               != digest({k: sorted(v, key=digest) if isinstance(v, list) else v for k, v in chain['database'].items()})):
        raise ValueError('fresh readonly endpoint or persisted material differs')


def preserve_caller_environment(function):
    """Cover pre-setup failures too, preserving stock hooks and caller cwd."""
    @wraps(function)
    async def guarded(*args, **kwargs):
        caller, directory = dict(os.environ), Path.cwd()
        try:
            return await function(*args, **kwargs)
        finally:
            os.environ.clear()
            os.environ.update(caller)
            os.chdir(directory)
    return guarded
