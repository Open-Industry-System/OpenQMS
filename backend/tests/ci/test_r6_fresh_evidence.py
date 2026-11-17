"""SYNTHETIC FORMAT tests only; these never constitute live C9 acceptance."""
import hashlib
import json
from pathlib import Path

import pytest

from tests.e2e import r6_fresh_evidence as evidence


def reference(path, data):
    path.write_bytes(data)
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}


def test_registered_verifier_checks_all_trust_edges_before_execution(tmp_path):
    repo = tmp_path / 'repo'
    module_path = repo / 'backend/tests/e2e/r6_fresh_readonly.py'
    module_path.parent.mkdir(parents=True)
    source = b'INTERFACE = "r6.c9-readonly.v1"\nMARKER = "SYNTHETIC_FORMAT_ONLY"\n'
    verifier = reference(module_path, source)
    descriptor = dict(verifier, interface=evidence.READONLY_INTERFACE)
    prepare = reference(tmp_path / 'prepare.py', ('R6_READONLY_VERIFIER = ' + repr(descriptor) + '\n').encode())
    values = {
        'resource': {'owner_nonce': 'synthetic-format-owner'},
        'operator_manifest': {'kind': 'r6.c9-operators.v1', 'owner': 'synthetic-format-owner', 'files': {'prepare.py': prepare}},
        'build_config': {'execution': {'operator_adapters': {'prepare.py': prepare['sha256']}}},
        'source_manifest': {'files': {'backend/tests/e2e/r6_fresh_readonly.py': verifier['sha256']}},
    }
    assert evidence.registered_verifier_bytes(values, verifier, repo=repo) == source

    from copy import deepcopy
    for change in ('unknown_operator', 'altered_hash', 'wrong_owner', 'missing_source', 'unsupported_interface', 'arbitrary_path', 'duplicate_descriptor'):
        broken = deepcopy(values)
        changed_ref = dict(verifier)
        if change == 'unknown_operator':
            broken['build_config']['execution']['operator_adapters'] = {}
        elif change == 'altered_hash':
            changed_ref['sha256'] = '0' * 64
        elif change == 'wrong_owner':
            broken['operator_manifest']['owner'] = 'another-owner'
        elif change == 'missing_source':
            broken['source_manifest']['files'] = {}
        else:
            changed = dict(descriptor)
            if change == 'unsupported_interface':
                changed['interface'] = 'unsupported'
            elif change == 'arbitrary_path':
                changed['path'] = str(tmp_path / 'arbitrary.py')
            body = 'R6_READONLY_VERIFIER = ' + repr(changed) + '\n'
            if change == 'duplicate_descriptor':
                body += body
            replacement = reference(tmp_path / 'prepare.py', body.encode())
            broken['operator_manifest']['files']['prepare.py'] = replacement
            broken['build_config']['execution']['operator_adapters']['prepare.py'] = replacement['sha256']
        with pytest.raises(ValueError):
            evidence.registered_verifier_bytes(broken, changed_ref, repo=repo)
        # Restore original actual operator bytes for the next independent mutant.
        reference(tmp_path / 'prepare.py', ('R6_READONLY_VERIFIER = ' + repr(descriptor) + '\n').encode())


@pytest.mark.parametrize('field,value', [('passed', True), ('selected', True), ('skipped', 1), ('failed', 1), ('errors', 1), ('xfailed', 1), ('xpassed', 1), ('exit_code', False)])
def test_single_live_receipt_rejects_truthy_and_nonpasses(field, value):
    receipt = dict(status='PASSED', exit_code=0, selected=1, passed=1, **{name: 0 for name in evidence.ZERO})
    evidence.passed_one(receipt)
    receipt[field] = value
    with pytest.raises(ValueError):
        evidence.passed_one(receipt)


def checker_module():
    import importlib.util
    path = Path(__file__).resolve().parents[3] / 'scripts/r6-compat-check.py'
    spec = importlib.util.spec_from_file_location('synthetic_compat_checker', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_disjoint_certificate_versions_preserve_strict_historical_c9(tmp_path):
    checker = checker_module()
    def saved(name, value):
        return reference(tmp_path / name, json.dumps(value).encode())
    failed = saved('failed.json', dict(status='FAILED', exit_code=1, failed=1, passed=0))
    manifest = saved('manifest.json', dict(external_evidence={'original': failed['sha256']}))
    summary = dict(status='COMPOSED_PASS', original_live_status='FAILED', evidence_method='COMPOSED_SAME_REPORT_SEQUENTIAL',
                   readonly_final={'manifest_sha256': manifest['sha256']})
    certificate = dict(kind='r6.compatibility-rehearsal.v1', status='PASS', production_authorized=False,
        c9=saved('c9.json', summary), c9_snapshot={}, c9_readonly_manifest=manifest,
        original_failed_receipt=failed, c10={}, internal_contracts={}, audit_baseline={}, generation_off_probe={})
    assert checker._validate_c9(certificate) == summary
    from copy import deepcopy
    for change in ('mixed_v1', 'mixed_v2', 'unknown', 'historical_relabel', 'fresh_old_label', 'production'):
        bad = deepcopy(certificate)
        if change == 'mixed_v1':
            bad['c9_execution'] = {}
        elif change == 'mixed_v2':
            bad['kind'] = 'r6.compatibility-rehearsal.v2'
        elif change == 'unknown':
            bad['kind'] = 'r6.compatibility-rehearsal.v3'
        elif change == 'historical_relabel':
            bad['c9'] = saved('relabel.json', dict(summary, status='PASS'))
        elif change == 'fresh_old_label':
            bad['kind'] = 'r6.compatibility-rehearsal.v2'
            bad['c9_execution'] = bad.pop('original_failed_receipt')
        else:
            bad['production_authorized'] = True
        with pytest.raises(ValueError):
            checker._validate_c9(bad)


def test_registered_source_rejected_before_dynamic_compile(tmp_path, monkeypatch):
    executed = []
    monkeypatch.setattr(evidence, 'validate_fresh_c9', lambda *args: {})
    def reject(*args):
        raise ValueError('SYNTHETIC_FORMAT unregistered helper')
    monkeypatch.setattr(evidence, 'registered_verifier_bytes', reject)
    monkeypatch.setattr('builtins.compile', lambda *args, **kwargs: executed.append(args))
    with pytest.raises(ValueError):
        evidence.trusted_readonly_verifier({}, {}, {}, {}, {})
    assert executed == []


def test_reader_module_has_no_top_level_application_activity():
    import ast
    path = Path(__file__).resolve().parents[1] / 'e2e/r6_fresh_readonly.py'
    tree = ast.parse(path.read_bytes())
    allowed_imports = {'hashlib', 'io', 'json', 'pathlib', 'uuid', 'zipfile', 'xml.etree'}
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed_imports for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed_imports
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            ast.literal_eval(node.value)
        else:
            assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or (
                isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))


def synthetic_chain():
    """Explicit data-format fiction; no app, model or acceptance receipt."""
    from uuid import UUID
    uid = lambda number: str(UUID(int=number))
    ids = dict(report_id=uid(1), d4_task=uid(2), d5_task=uid(3), measure_id=uid(4), a=uid(5), b=uid(6))
    prepared, models, entries, tasks = {}, {'task_bindings': [], 'runs': []}, {}, {}
    audit = []
    for index, name in enumerate(('d4', 'd5'), 1):
        installation, deployment, run, attempt = [uid(index * 100 + offset) for offset in range(1, 5)]
        profile = 'model_d4_candidate_v1' if name == 'd4' else 'model_d5_proposal_r6_v1'
        prepared[name] = dict(profile=profile, installation_id=installation, model_deployment_id=deployment,
                              policy=dict(profile=profile, plugin_version='synthetic-format-v1'))
        model = dict(deployment_id=deployment, kind='cloud', provider='openai', api_protocol='responses',
                     model='gpt-6.1-terra', base_url='https://api.openai.com/v1',
                     credential_ref='r5-env:R5_MODEL_CREDENTIAL_OPENAI_TRIAL', allowed_addresses=['8.8.8.8'],
                     version='synthetic-format-v1', config_hmac='synthetic-format-only-not-signed')
        models[name] = model
        task = dict(task_id=ids[name + '_task'], target_capa_id=ids['report_id'], preferred_installation_id=installation,
                    model_deployment=dict(deployment_id=deployment))
        tasks[name] = task
        entries[name] = dict(creation=dict(task=task, command=dict(report_id=ids['report_id'])),
                             launch=dict(status=200, body=dict(task_id=task['task_id'])),
                             completion=dict(status='completed', task_id=task['task_id']))
        models['task_bindings'].append(dict(task_id=task['task_id'], deployment_id=deployment, config_hmac=model['config_hmac']))
        models['runs'].append(dict(run_id=run, task_id=task['task_id'], installation_id=installation))
        fields = dict(task_id=task['task_id'], run_id=run, deployment_id=deployment, version=model['version'])
        audit.extend([dict(action='MODEL_EGRESS_ATTEMPT', log_id=attempt, record_id=deployment,
                           changed_fields=dict(fields, snapshot_hmac='synthetic-only')),
                      dict(action='MODEL_EGRESS_COMPLETED', log_id=uid(index * 100 + 5), record_id=deployment,
                           correlation_id=attempt, changed_fields=fields)])
    for row in audit:
        fields = row['changed_fields']
        if fields['task_id'] == ids['d4_task']:
            fields.pop('version')
            fields.pop('snapshot_hmac', None)
        elif row['action'] == 'MODEL_EGRESS_ATTEMPT':
            fields['snapshot_hmac'] = 'f' * 64
        if row['action'] == 'MODEL_EGRESS_ATTEMPT':
            row['correlation_id'] = None if fields['task_id'] == ids['d4_task'] else fields['run_id']
        row.update(table_name='agent_model_deployments', operated_at='2099-01-01T00:00:00+00:00',
            operated_by=uid(50), factory_id=uid(51), old_values=None, new_values=None,
            ip_address=None, user_agent=None, tenant_schema=None)
    proposals = [dict(proposal_id=ids[name], task_id=ids['d5_task'], original_text='SYNTHETIC_FORMAT_ONLY ' + name,
                      state='pending') for name in ('a', 'b')]
    checkpoint = dict(checkpoint_id=uid(8))
    entries['d5']['checkpoint'] = checkpoint
    d4, d5 = dict(task=tasks['d4']), dict(task=tasks['d5'], proposals=proposals, checkpoint=checkpoint)
    review = dict(report_id=ids['report_id'], task_id=ids['d5_task'], selected_proposal_id=ids['a'],
                  reviewed_existing_control=True, reason='SYNTHETIC_FORMAT_ONLY review',
                  original_text_hashes={row['proposal_id']: hashlib.sha256(row['original_text'].encode()).hexdigest() for row in proposals})
    wrap = lambda rows: [dict(body=row) for row in rows]
    sources = [dict(report_id=ids['report_id'], projection_id=projection) for projection in (
        'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1', 'fmea.failure_cause.reference.v1')]
    verification = dict(verification_id=uid(9), source_proof_issued=True)
    revision = dict(revision_id=uid(10), measure_id=ids['measure_id'], revision_no=1)
    database = dict(audit=audit, commands=[dict(command_id=uid(20 + i), task_id=ids['d5_task'], proposal_id=ids[name], sequence=i + 2)
                                          for i, name in enumerate(('a', 'b'))], checkpoint_watermark=1,
        capa_d5_proposals=wrap([dict(row, report_id=ids['report_id'], state=state)
                              for row, state in zip(proposals, ('adopted', 'withdrawn'))]),
        capa_d5_measures=wrap([dict(measure_id=ids['measure_id'], proposal_id=ids['a'])]),
        correction_revisions=[revision], capa_r6_source_origins=wrap(sources),
        capa_d4_candidates=wrap([dict(report_id=ids['report_id'])]),
        agent_d4_input_receipts=wrap([dict(report_id=ids['report_id'])]),
        agent_d5_basis_receipts=wrap([dict(report_id=ids['report_id'])]),
        capa_d4_root_cause_source_proofs=wrap([dict(report_id=ids['report_id'], revision_id=uid(11), proof_id=uid(12), status='active', verification_id=uid(9))]),
        complete_root_delivery=[dict(report_id=ids['report_id'], revision_id=uid(11))])
    final = dict(binding_status='verified', contract='capa.outcome-review.v2', d5_measures=[dict(measure_id=ids['measure_id'])],
                 local_closure=dict(propagation=dict(channels={name: 'NOT_EXECUTED' for name in ('knowledge', 'supplier', 'lesson', 'lateral')})))
    chain = dict(ids, live_provider=True, history=dict(corrections=[revision]), verification=verification,
                 withdrawal={}, review=final, manual_d5='SYNTHETIC_FORMAT_ONLY', adoption_loss={}, adoption_replay={},
                 database=database, receipts=[], switch={}, browser_model_entries=entries)
    return chain, d4, d5, prepared, models, review


def test_fresh_chain_cross_references_actual_records_not_truthy_summary():
    from copy import deepcopy
    original = synthetic_chain()
    assert evidence.validate_chain(*original)['report_id'] == original[0]['report_id']
    for change in ('controlled', 'truthy_live', 'wrong_report', 'launch_task', 'incomplete', 'model', 'profile',
                   'review_truthy', 'review_old_proposal', 'text_hash', 'duplicate_command', 'pre_checkpoint',
                   'proposal_binding', 'missing_proposal', 'immutable_text', 'correction', 'source_missing',
                   'source_other_report', 'proof', 'delivery', 'missing_completion', 'extra_completion',
                   'wrong_model_audit', 'wrong_run', 'task_binding', 'completion_payload', 'propagation'):
        chain, d4, d5, prepared, models, review = args = deepcopy(original)
        if change == 'controlled': chain['live_provider'] = False
        elif change == 'truthy_live': chain['live_provider'] = 1
        elif change == 'wrong_report': d4['task']['target_capa_id'] = chain['a']
        elif change == 'launch_task': chain['browser_model_entries']['d4']['launch']['body']['task_id'] = chain['a']
        elif change == 'incomplete': chain['browser_model_entries']['d5']['completion']['status'] = 'running'
        elif change == 'model': models['d5']['kind'] = 'local'
        elif change == 'profile': prepared['d4']['policy']['profile'] = 'model_d5_proposal_r6_v1'
        elif change == 'review_truthy': review['reviewed_existing_control'] = 1
        elif change == 'review_old_proposal': review['selected_proposal_id'] = chain['b']
        elif change == 'text_hash': review['original_text_hashes'][chain['a']] = '0' * 64
        elif change == 'duplicate_command': chain['database']['commands'][1] = chain['database']['commands'][0]
        elif change == 'pre_checkpoint': chain['database']['commands'][0]['sequence'] = 1
        elif change == 'proposal_binding': chain['database']['commands'][0]['proposal_id'] = chain['measure_id']
        elif change == 'missing_proposal': d5['proposals'].pop()
        elif change == 'immutable_text': chain['database']['capa_d5_proposals'][0]['body']['original_text'] += 'changed'
        elif change == 'correction': chain['database']['correction_revisions'][0]['revision_no'] = 2
        elif change == 'source_missing': chain['database']['capa_r6_source_origins'].pop()
        elif change == 'source_other_report': chain['database']['capa_r6_source_origins'][0]['body']['report_id'] = chain['b']
        elif change == 'proof': chain['verification']['source_proof_issued'] = 1
        elif change == 'delivery': chain['database']['complete_root_delivery'][0]['revision_id'] = chain['b']
        elif change == 'missing_completion': chain['database']['audit'].pop()
        elif change == 'extra_completion': chain['database']['audit'].append(chain['database']['audit'][-1])
        elif change == 'wrong_model_audit': chain['database']['audit'][0]['record_id'] = chain['b']
        elif change == 'wrong_run': models['runs'][0]['installation_id'] = chain['b']
        elif change == 'task_binding': models['task_bindings'][0]['config_hmac'] = 'changed'
        elif change == 'completion_payload': chain['database']['audit'][1]['changed_fields']['body'] = 'forbidden'
        elif change == 'propagation': chain['review']['local_closure']['propagation']['channels']['supplier'] = 'EXECUTED'
        with pytest.raises(ValueError):
            evidence.validate_chain(*args)


def synthetic_provenance(tmp_path, monkeypatch):
    """Create a local SYNTHETIC FORMAT repository; no database/provider exists."""
    import hmac
    import subprocess
    repo = tmp_path / 'synthetic-repo'
    repo.mkdir()
    paths = ['backend/tests/e2e/r6_live_harness.py', 'backend/tests/e2e/r6_exercise.py',
             'backend/tests/e2e/test_r6_live_chain.py', 'backend/tests/e2e/test_r6_entry_switch_browser.py',
             'backend/tests/e2e/test_r6_entry_switch_process.py', 'backend/tests/capa/r6_switch_support.py',
             'backend/tests/capa/r6_support.py', 'frontend/playwright.agent.config.ts',
             'frontend/e2e/specs/capa/r6-entry-switch.spec.ts', 'backend/tests/e2e/r6_fresh_readonly.py']
    files = {}
    for name in paths:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        files[name] = reference(path, b'"SYNTHETIC_FORMAT_ONLY"\n')['sha256']
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(['git', '-c', 'user.name=Synthetic Format', '-c', 'user.email=synthetic@invalid',
                    'commit', '-qm', 'SYNTHETIC FORMAT ONLY'], cwd=repo, check=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    directory = tmp_path / 'owned-format-only'
    directory.mkdir()
    source = dict(kind='r6.executed-sources.v1', repository_root=str(repo), source_revision=revision,
                  files=files, external_files={}, executables={}, packages={})
    for name in ('python', 'node', 'browser'):
        source['executables'][name] = reference(directory / name, ('SYNTHETIC NOT EXECUTABLE ' + name).encode())
    owner = 'synthetic-format-owner'
    resource_ref = reference(directory / 'resource.json', json.dumps(dict(owner_nonce=owner, test_database='synthetic_test')).encode())
    candidate = dict(SECRET_KEY='synthetic-format-only-model-key', OPENQMS_TEST_RESOURCE_FILE=resource_ref['path'])
    key = 'synthetic-format-only-authority-key'
    monkeypatch.setenv('R6_SWITCH_AUTHORITY_KEY', key)
    monkeypatch.setenv('OPENQMS_TEST_RESOURCE_FILE', resource_ref['path'])
    operators = {name: reference(directory / name, b'"SYNTHETIC_FORMAT_ONLY"\n') for name in ('prepare.py', 'live.py', 'run.py')}
    configurations = {name: reference(directory / ('environment.json' if name == 'candidate' else 'environment.compat.json'), json.dumps(candidate).encode()) for name in ('candidate', 'compatible')}
    target = dict(owner=owner, database='synthetic_test', deployment_role='synthetic_exercise', environment='isolated_exercise',
                  tenant=dict(tenant_id='00000000-0000-0000-0000-000000000001', schema='tenant_synthetic', generation=1), environment_id='synthetic-format',
                  public_head='synthetic_public_head', tenant_head='synthetic_tenant_head')
    execution_config = dict(execution_artifacts={name: files[name] for name in paths[:-1]},
        node=source['executables']['node'], chromium=source['executables']['browser'], backend_packages={},
        frontend_dependencies={}, operator_adapters={name: ref['sha256'] for name, ref in operators.items()},
        deployment_configurations=configurations)
    for name in ('openai', 'httpx', 'httpcore'):
        package_file = reference(directory / (name + '.py'), b'"SYNTHETIC FORMAT SDK"\n')
        source['external_files'][package_file['path']] = package_file['sha256']
        package = dict(version='synthetic-format-only', sources={name + '.py': package_file['sha256']})
        source['packages'][name] = dict(package, root=str(directory))
        execution_config['backend_packages'][name] = package
    config = dict(owner=owner, tenant=target['tenant'], environment_id=target['environment_id'], execution=execution_config)
    config_ref = reference(directory / 'config.json', json.dumps(config).encode())
    target['config_digest'] = config_ref['sha256']
    build = dict(source_manifest=files, source_root=str(repo), source_revision=revision,
                 executable=source['executables']['python']['path'], executable_digest=source['executables']['python']['sha256'],
                 schema_heads=[target['public_head'], target['tenant_head']], config_digest=target['config_digest'])
    target.update(candidate_build=evidence.digest(build), compatible_build=evidence.digest(build), source_manifest=evidence.digest(files))
    build_ref = reference(directory / 'build.json', json.dumps(build).encode())
    record = dict(target=target, resource_record=resource_ref['path'], config_file=config_ref['path'],
                  build_artifacts={target['candidate_build']: build_ref})
    authority = dict(record=record, signature=hmac.new(key.encode(), evidence.digest(record).encode(), hashlib.sha256).hexdigest())
    chain, d4, d5, prepared, models, review = synthetic_chain()
    chain['switch'] = dict(target=target)
    # Calculate the production domains on clearly fictional files and values.
    for name in ('d4', 'd5'):
        policy = dict(artifact=source['executables']['node']['path'], artifact_sha256=source['executables']['node']['sha256'],
                      interpreter=source['executables']['python']['path'], interpreter_sha256=source['executables']['python']['sha256'],
                      launcher_sha256='f' * 64, tenant_id=target['tenant']['tenant_id'], tenant_generation=1,
                      installation_id=prepared[name]['installation_id'], credential_epoch=1, plugin_version='synthetic-format-v1',
                      platform_port=12345, expires_at='2099-01-01T00:00:00+00:00', profile=prepared[name]['profile'])
        prepared[name]['policy'] = policy
        from datetime import datetime
        fingerprint = dict(approval={key: policy[key] for key in ('artifact', 'artifact_sha256', 'interpreter', 'interpreter_sha256', 'launcher_sha256')},
            **{key: policy[key] for key in ('tenant_id', 'tenant_generation', 'installation_id', 'credential_epoch', 'plugin_version', 'platform_port', 'profile')},
            expires_at=str(datetime.fromisoformat(policy['expires_at'])))
        models[name].update(enabled=True, tenant_generation=1, created_by='synthetic-actor', name='synthetic-format-only',
            executor_pins=dict(policy_sha256=evidence.digest(fingerprint), artifact_sha256=policy['artifact_sha256'],
                interpreter_sha256=policy['interpreter_sha256'], launcher_sha256=policy['launcher_sha256'], profile=policy['profile']))
        fields = ('deployment_id', 'name', 'version', 'tenant_generation', 'kind', 'provider', 'model', 'base_url',
                  'allowed_addresses', 'credential_ref', 'executor_pins', 'created_by')
        signed = {key: models[name][key] for key in fields}
        signed.update(tenant_id=target['tenant']['tenant_id'], api_protocol='responses')
        models[name]['config_hmac'] = hmac.new(candidate['SECRET_KEY'].encode(), b'openqms.r5.model-deployment.v1\n' +
            json.dumps(signed, sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()
    values = dict(source_manifest=source, authority=authority, switch_environment=dict(R6_SWITCH_AUTHORITY_KEY=key),
        build=build, build_config=config, chain=chain, resource=dict(owner_nonce=owner, test_database='synthetic_test'),
        operator_manifest=dict(kind='r6.c9-operators.v1', owner=owner, files=operators), prepared=prepared, models=models)
    authority_ref = reference(directory / 'authority.json', json.dumps(authority).encode())
    monkeypatch.setenv('R6_SWITCH_AUTHORITY_FILE', authority_ref['path'])
    execution = dict(resource=resource_ref, build=build_ref, build_config=config_ref, authority=authority_ref)
    return values, candidate, configurations, execution, repo


def test_provenance_binds_source_owner_config_build_operators_and_normal_pins(tmp_path, monkeypatch):
    from copy import deepcopy
    original = synthetic_provenance(tmp_path, monkeypatch)
    evidence.validate_provenance(*original[:4], repo=original[4])
    for change in ('source_omitted', 'helper_hash', 'source_revision', 'authority', 'owner', 'target', 'config',
                   'build', 'schema', 'runtime_source', 'app_artifact', 'python', 'node', 'sdk', 'operator',
                   'operator_owner', 'model_hmac', 'pins', 'tenant', 'private_dns', 'disabled', 'approved_profile'):
        values, candidate, configurations, execution, repo = deepcopy(original)
        if change == 'source_omitted': values['source_manifest']['files'].pop('backend/tests/e2e/r6_fresh_readonly.py')
        elif change == 'helper_hash': values['source_manifest']['files']['backend/tests/e2e/r6_fresh_readonly.py'] = '0' * 64
        elif change == 'source_revision': values['source_manifest']['source_revision'] = '0' * 40
        elif change == 'authority': values['authority']['signature'] = '0' * 64
        elif change == 'owner': values['resource']['owner_nonce'] = 'another-owner'
        elif change == 'target': values['chain']['switch']['target']['environment'] = 'formal'
        elif change == 'config': execution['build_config']['sha256'] = '0' * 64
        elif change == 'build': values['build']['executable_digest'] = '0' * 64
        elif change == 'schema': values['build']['schema_heads'] = ['other', 'schema']
        elif change == 'runtime_source': values['build']['source_manifest'] = {}
        elif change == 'app_artifact': values['build_config']['execution']['execution_artifacts'] = {}
        elif change == 'python': values['source_manifest']['executables']['python']['sha256'] = '0' * 64
        elif change == 'node': values['build_config']['execution']['node']['sha256'] = '0' * 64
        elif change == 'sdk': values['source_manifest']['packages']['openai']['version'] = 'another'
        elif change == 'operator': values['build_config']['execution']['operator_adapters']['prepare.py'] = '0' * 64
        elif change == 'operator_owner': values['operator_manifest']['owner'] = 'another-owner'
        elif change == 'model_hmac': values['models']['d4']['config_hmac'] = '0' * 64
        elif change == 'pins': values['models']['d4']['executor_pins']['profile'] = 'arbitrary'
        elif change == 'tenant': values['models']['d5']['tenant_generation'] = 2
        elif change == 'private_dns': values['models']['d4']['allowed_addresses'] = ['127.0.0.1']
        elif change == 'disabled': values['models']['d4']['enabled'] = False
        elif change == 'approved_profile': values['prepared']['d4']['policy']['profile'] = 'arbitrary'
        with pytest.raises(ValueError):
            evidence.validate_provenance(values, candidate, configurations, execution, repo=repo)


def synthetic_full_execution(tmp_path, monkeypatch):
    """Entirely fictional receipt bytes, explicitly unit format data only."""
    import hmac
    from copy import deepcopy
    from app.services.capa_switch_evidence import Document
    values, candidate, configurations, execution, repo = synthetic_provenance(tmp_path, monkeypatch)
    directory = Path(execution['resource']['path']).parent
    def saved(name, value):
        return reference(directory / name, json.dumps(value).encode())
    values['resource'].update(host='127.0.0.1', r6_exercise_directory=str(directory), r6_c9_execution_id='00000000-0000-0000-0000-000000000055')
    execution['resource'] = saved('resource.json', values['resource'])
    candidate['R6_GENERATION_ENABLED'] = 'true'
    candidate['AGENT_R5_CONTROLLED_POLICY_FILE'] = str(directory / 'policy.json')
    values['policy'] = values['prepared']['d5']['policy']
    policy_ref = saved('policy.json', values['policy'])
    values['session'] = dict(report_id=values['chain']['report_id'], tenant_id=values['chain']['switch']['target']['tenant']['tenant_id'],
        schema=values['chain']['switch']['target']['tenant']['schema'], generation=values['chain']['switch']['target']['tenant']['generation'],
        actors={'qe': {'user_id': '00000000-0000-0000-0000-000000000032'}}, factory_id='00000000-0000-0000-0000-000000000033')
    values['build_config']['execution']['enrollments'] = [dict(profile='model_d5_proposal_r6_v1', policy_sha256=policy_ref['sha256'])]
    configurations['candidate'] = saved('environment.json', candidate)
    configurations['compatible'] = saved('environment.compat.json', dict(candidate, R6_GENERATION_ENABLED='false'))
    reader_ref = {'path': str(repo / 'backend/tests/e2e/r6_fresh_readonly.py'),
                  'sha256': values['source_manifest']['files']['backend/tests/e2e/r6_fresh_readonly.py']}
    descriptor = dict(reader_ref, interface=evidence.READONLY_INTERFACE)
    prepare = reference(directory / 'prepare.py', ('R6_READONLY_VERIFIER = ' + repr(descriptor) + '\n').encode())
    values['operator_manifest']['files']['prepare.py'] = prepare
    values['build_config']['execution']['operator_adapters']['prepare.py'] = prepare['sha256']
    target = values['chain']['switch']['target']
    target.update(system_identifier='123456789', database_role='synthetic_operator')
    execution['build_config'] = saved('config.json', values['build_config'])
    target['config_digest'] = values['build']['config_digest'] = execution['build_config']['sha256']
    target.update(candidate_build=evidence.digest(values['build']), compatible_build=evidence.digest(values['build']))
    execution['build'] = saved('build.json', values['build'])
    record = values['authority']['record']
    record['build_artifacts'] = {target['candidate_build']: execution['build']}
    operation, exercise = '00000000-0000-0000-0000-000000000033', '00000000-0000-0000-0000-000000000044'
    initial = dict(version=1, kind='exercise_input', purpose='r6-rehearsal.v1', exercise_id=exercise,
                   expires_at='2099-01-01T00:00:00+00:00', target=target, initial_epoch=0)
    canonical = lambda document: evidence.digest(Document.model_validate(document).model_dump(mode='json', by_alias=True))
    first_digest = canonical(initial)
    renewed = dict(initial, resume_of=dict(operation_ref=operation, previous_document_digest=first_digest, draining_epoch=7))
    final_digest = canonical(renewed)
    accepted = dict(stage='switched-confirmed', exercise_id=exercise, operation_ref=operation, closed_epoch=7,
        initial_document=dict(saved('exercise-initial.json', initial), canonical_digest=first_digest),
        renewed_document=dict(saved('exercise-renewed.json', renewed), canonical_digest=final_digest),
        accepted=dict(state='switched', epoch=9, operation_ref=operation, document_digest=final_digest))
    accepted_ref = saved('accepted.json', accepted)
    values['chain']['switch'].update(exercise_authority_chain=accepted_ref, operation=operation,
        current_accepted_document_digest=final_digest, original_exercise_digest=first_digest)
    record['authorized_documents'] = [first_digest, final_digest]
    key = values['switch_environment']['R6_SWITCH_AUTHORITY_KEY']
    values['authority']['signature'] = hmac.new(key.encode(), evidence.digest(record).encode(), hashlib.sha256).hexdigest()
    for binding in values['models']['task_bindings']:
        name = 'd4' if binding['task_id'] == values['chain']['d4_task'] else 'd5'
        binding['config_hmac'] = values['models'][name]['config_hmac']
    chain, d4, d5, _, _, review = synthetic_chain()
    values['d4_model'], values['d5_model'], values['employee_review'] = d4, d5, review
    enrich_input_receipts(values)
    values['chain']['verification']['root_cause_text'] = 'SYNTHETIC_FORMAT_ONLY'
    values['receipt'] = dict(layer='live', status='PASSED', frozen_sha=values['source_manifest']['source_revision'], exit_code=0, selected=1, passed=1,
        **{name: 0 for name in evidence.ZERO}, command=[values['source_manifest']['executables']['python']['path'],
        '-m', 'tests.ci.pytest_bootstrap', 'tests/e2e/test_r6_live_chain.py', '-m', 'live_provider', '-q',
        '--tb=short', '-rA', '--junitxml=<private>', '-p', 'tests.ci.gate_results', '-o', 'faulthandler_timeout=120'])
    values['hooks'] = {name: values['receipt'][name] for name in ('selected', 'passed', *evidence.ZERO)}
    values['attempt'] = dict(stage='approved-and-preserved', report_id=values['chain']['report_id'])
    values['accepted_switch'] = accepted
    values['switch'] = deepcopy(values['chain']['switch'])
    execution['kind'] = evidence.EXECUTION_KIND
    execution['execution_id'] = values['resource']['r6_c9_execution_id']
    execution['configurations'] = configurations
    for name in ('receipt', 'hooks', 'chain', 'attempt', 'source_manifest', 'operator_manifest', 'resource', 'prepared',
                 'models', 'employee_review', 'd4_model', 'd5_model', 'accepted_switch', 'authority', 'build', 'build_config', 'switch_environment', 'switch', 'session', 'policy'):
        filename = {'build_config': 'config.json', 'switch_environment': 'switch-environment.json',
            'chain': 'c9-evidence.json', 'd4_model': 'd4-model.json', 'd5_model': 'd5-model.json',
            'attempt': 'live-attempt.json', 'switch': 'build-and-switch.json'}.get(name, name + '.json')
        execution[name] = saved(filename, values[name])
    execution['accepted_switch'] = accepted_ref
    from xml.etree import ElementTree
    root = ElementTree.Element('testsuites')
    case = ElementTree.SubElement(ElementTree.SubElement(root, 'testsuite'), 'testcase', classname=evidence.LIVE_CLASS, name=evidence.LIVE_TEST)
    binding = dict(kind='r6.live-test-binding.v1', source_revision=values['source_manifest']['source_revision'],
        execution_id=execution['execution_id'], owner_nonce=values['resource']['owner_nonce'], report_id=values['chain']['report_id'],
        resource=execution['resource'], candidate_configuration=configurations['candidate'],
        **{key: execution[key] for key in ('chain', 'd4_model', 'd5_model', 'attempt', 'switch')})
    ElementTree.SubElement(ElementTree.SubElement(case, 'properties'), 'property', name='r6_live_binding', value=json.dumps(binding))
    execution['junit'] = reference(directory / 'live.xml', ElementTree.tostring(root))
    # Config/resource/build exact registered paths must match their actual refs.
    record['resource_record'], record['config_file'] = execution['resource']['path'], execution['build_config']['path']
    record['build_artifacts'] = {target['candidate_build']: execution['build']}
    values['authority']['signature'] = hmac.new(key.encode(), evidence.digest(record).encode(), hashlib.sha256).hexdigest()
    execution['authority'] = saved('authority.json', values['authority'])
    execution_ref = saved('execution.json', execution)
    snapshot = dict(report_id=values['chain']['report_id'], measure_id=values['chain']['measure_id'], a=values['chain']['a'],
        b=values['chain']['b'], current=dict(status='D8_CLOSURE'), original_switch=values['chain']['switch'],
        history=values['chain']['history'], review=values['chain']['review'], verification=[{k: v for k, v in values['chain']['verification'].items() if k != 'source_proof_issued'}],
        database=values['chain']['database'], immutable_original_model=dict(agent_tasks=[dict(
            task_id=values['chain']['d4_task'], executor_user_id=values['session']['actors']['qe']['user_id'])]))
    snapshot_ref = saved('snapshot.json', snapshot)
    manifest = dict(kind='r6.c9-readonly-manifest.v1', execution=execution_ref, readonly_verifier=reader_ref,
                    external_evidence={execution['receipt']['path']: execution['receipt']['sha256']})
    manifest_ref = saved('readonly-manifest.json', manifest)
    summary = dict(kind=evidence.FRESH_KIND, status='PASS', evidence_method='FRESH_SINGLE_PASS', report_id=snapshot['report_id'],
                   execution=execution_ref, readonly_final=dict(manifest_sha256=manifest_ref['sha256'], evidence_sha256=snapshot_ref['sha256']))
    return summary, execution_ref, manifest_ref, snapshot_ref, repo


def test_full_fresh_format_positive_and_original_node_binding(tmp_path, monkeypatch):
    proof = synthetic_full_execution(tmp_path, monkeypatch)
    assert evidence.validate_fresh_c9(*proof[:4], repo=proof[4])['receipt']['status'] == 'PASSED'


@pytest.mark.parametrize('change', (
    'summary_unknown', 'old_label', 'summary_report', 'execution_unknown', 'mixed_failed_ref',
    'receipt_skip', 'receipt_truthy', 'receipt_command', 'receipt_old_source', 'hook_error', 'missing_node', 'wrong_node', 'junit_error',
    'controlled', 'completed_missing', 'attempt_report', 'build_source', 'config_hash', 'source_helper',
    'model_approval', 'snapshot_report', 'snapshot_history', 'snapshot_database', 'manifest_unknown', 'reader_hash',
    'owner', 'accepted_epoch', 'document_bytes'))
def test_full_fresh_format_rejects_missing_or_mismatched_bindings(tmp_path, monkeypatch, change):
    summary, execution_ref, manifest_ref, snapshot_ref, repo = synthetic_full_execution(tmp_path, monkeypatch)
    execution, manifest, snapshot = evidence.load(execution_ref), evidence.load(manifest_ref), evidence.load(snapshot_ref)
    directory = Path(execution_ref['path']).parent
    def saved(name, value):
        return reference(directory / name, json.dumps(value).encode())
    def changed(key, modify):
        value = evidence.load(execution[key])
        modify(value)
        execution[key] = saved('mutant-' + key + '.json', value)
    if change == 'summary_unknown': summary['original_live_status'] = 'FAILED'
    elif change == 'old_label': summary['evidence_method'] = 'COMPOSED_SAME_REPORT_SEQUENTIAL'
    elif change == 'summary_report': summary['report_id'] = snapshot['b']
    elif change == 'execution_unknown': execution['synthetic_unbound'] = True
    elif change == 'mixed_failed_ref': execution['original_failed_receipt'] = execution['receipt']
    elif change == 'receipt_skip': changed('receipt', lambda value: value.update(skipped=1))
    elif change == 'receipt_truthy': changed('receipt', lambda value: value.update(passed=True))
    elif change == 'receipt_command': changed('receipt', lambda value: value['command'].append('--ignore=required'))
    elif change == 'receipt_old_source': changed('receipt', lambda value: value.update(frozen_sha='0' * 40))
    elif change == 'hook_error': changed('hooks', lambda value: value.update(errors=1))
    elif change == 'missing_node': execution['junit'] = reference(directory / 'mutant.xml', b'<testsuites/>')
    elif change == 'wrong_node':
        execution['junit'] = reference(directory / 'mutant.xml', b'<testsuite><testcase classname="controlled" name="fake"/></testsuite>')
    elif change == 'junit_error':
        raw = evidence.read_bytes(execution['junit']).replace(b'</testcase>', b'<error/></testcase>')
        execution['junit'] = reference(directory / 'mutant.xml', raw)
    elif change == 'controlled': changed('chain', lambda value: value.update(live_provider=False))
    elif change == 'completed_missing': changed('chain', lambda value: value['browser_model_entries']['d5']['completion'].update(status='running'))
    elif change == 'attempt_report': changed('attempt', lambda value: value.update(report_id=snapshot['b']))
    elif change == 'build_source': changed('build', lambda value: value.update(source_revision='0' * 40))
    elif change == 'config_hash': execution['build_config']['sha256'] = '0' * 64
    elif change == 'source_helper': changed('source_manifest', lambda value: value['files'].update({'backend/tests/e2e/r6_fresh_readonly.py': '0' * 64}))
    elif change == 'model_approval': changed('models', lambda value: value['d4'].update(config_hmac='0' * 64))
    elif change == 'snapshot_report': snapshot['report_id'] = snapshot['b']
    elif change == 'snapshot_history': snapshot['history']['corrections'] = []
    elif change == 'snapshot_database': snapshot['database']['capa_r6_source_origins'] = []
    elif change == 'manifest_unknown': manifest['original_failed_receipt'] = execution['receipt']
    elif change == 'reader_hash': manifest['readonly_verifier']['sha256'] = '0' * 64
    elif change == 'owner': changed('resource', lambda value: value.update(owner_nonce='another-owner'))
    elif change == 'accepted_epoch': changed('accepted_switch', lambda value: value['accepted'].update(epoch=3))
    elif change == 'document_bytes':
        accepted = evidence.load(execution['accepted_switch'])
        Path(accepted['renewed_document']['path']).write_text('{}')
    new_execution = saved('mutant-execution.json', execution)
    summary['execution'] = new_execution
    manifest['execution'] = new_execution
    manifest['external_evidence'] = {execution['receipt']['path']: execution['receipt']['sha256']}
    manifest_ref, snapshot_ref = saved('mutant-manifest.json', manifest), saved('mutant-snapshot.json', snapshot)
    summary['readonly_final'] = dict(manifest_sha256=manifest_ref['sha256'], evidence_sha256=snapshot_ref['sha256'])
    with pytest.raises(ValueError):
        evidence.validate_fresh_c9(summary, new_execution, manifest_ref, snapshot_ref, repo=repo)


@pytest.mark.parametrize('change', ('missing', 'duplicate', 'wrong_test', 'unknown', 'owner', 'report', 'nonce',
                                   'config', 'chain', 'switch', 'duplicate_json', 'nonfinite', 'controlled_kind'))
def test_actual_completed_node_binding_rejects_spliced_properties(tmp_path, monkeypatch, change):
    from xml.etree import ElementTree
    summary, execution_ref, manifest_ref, snapshot_ref, repo = synthetic_full_execution(tmp_path, monkeypatch)
    execution, manifest = evidence.load(execution_ref), evidence.load(manifest_ref)
    root = ElementTree.fromstring(evidence.read_bytes(execution['junit']))
    case = next(root.iter('testcase'))
    properties = case.find('properties')
    prop = properties.find('property')
    value = json.loads(prop.get('value'))
    if change == 'missing': properties.remove(prop)
    elif change == 'duplicate': ElementTree.SubElement(properties, 'property', prop.attrib)
    elif change == 'wrong_test':
        case.remove(properties)
        root.find('testsuite').append(properties)
    elif change == 'duplicate_json': prop.set('value', '{"kind":"one","kind":"two"}')
    elif change == 'nonfinite': prop.set('value', '{"value":NaN}')
    else:
        if change == 'unknown': value['unbound'] = True
        elif change == 'owner': value['owner_nonce'] = 'another-owner'
        elif change == 'report': value['report_id'] = '00000000-0000-0000-0000-000000000066'
        elif change == 'nonce': value['execution_id'] = '00000000-0000-0000-0000-000000000067'
        elif change == 'controlled_kind': value['kind'] = 'r6.controlled-test-binding.v1'
        else:
            key = 'candidate_configuration' if change == 'config' else change
            value[key]['sha256'] = '0' * 64
        prop.set('value', json.dumps(value))
    directory = Path(execution_ref['path']).parent
    execution['junit'] = reference(directory / 'mutant-property.xml', ElementTree.tostring(root))
    execution_ref = reference(directory / 'mutant-property-execution.json', json.dumps(execution).encode())
    summary['execution'] = manifest['execution'] = execution_ref
    manifest_ref = reference(directory / 'mutant-property-manifest.json', json.dumps(manifest).encode())
    summary['readonly_final']['manifest_sha256'] = manifest_ref['sha256']
    with pytest.raises(ValueError):
        evidence.validate_fresh_c9(summary, execution_ref, manifest_ref, snapshot_ref, repo=repo)


def test_selfsigned_replacement_context_rejected_before_reader_compile(tmp_path, monkeypatch):
    import hmac
    summary, execution_ref, manifest_ref, snapshot_ref, repo = synthetic_full_execution(tmp_path, monkeypatch)
    execution, manifest = evidence.load(execution_ref), evidence.load(manifest_ref)
    directory = Path(execution_ref['path']).parent
    forged_key = 'attacker-self-selected-synthetic-key'
    authority = evidence.load(execution['authority'])
    authority['signature'] = hmac.new(forged_key.encode(), evidence.digest(authority['record']).encode(), hashlib.sha256).hexdigest()
    execution['authority'] = reference(directory / 'selfsigned-authority.json', json.dumps(authority).encode())
    execution['switch_environment'] = reference(directory / 'selfsigned-keys.json', json.dumps(dict(R6_SWITCH_AUTHORITY_KEY=forged_key)).encode())
    execution_ref = reference(directory / 'selfsigned-execution.json', json.dumps(execution).encode())
    summary['execution'] = manifest['execution'] = execution_ref
    manifest_ref = reference(directory / 'selfsigned-manifest.json', json.dumps(manifest).encode())
    summary['readonly_final']['manifest_sha256'] = manifest_ref['sha256']
    entered = []
    def forbidden_loader(*args, **kwargs):
        entered.append(True)
        raise AssertionError('untrusted source must never reach reader loading')
    monkeypatch.setattr(evidence, 'registered_verifier_bytes', forbidden_loader)
    with pytest.raises(ValueError, match='independently selected'):
        evidence.validate_fresh_c9(summary, execution_ref, manifest_ref, snapshot_ref, repo=repo)
    assert entered == []


def test_registered_python_alias_uses_same_verified_binary(tmp_path, monkeypatch):
    summary, execution_ref, manifest_ref, snapshot_ref, repo = synthetic_full_execution(tmp_path, monkeypatch)
    execution, manifest = evidence.load(execution_ref), evidence.load(manifest_ref)
    directory = Path(execution_ref['path']).parent
    python = Path(evidence.load(execution['source_manifest'])['executables']['python']['path'])
    alias = directory / 'verified-venv-python'
    alias.symlink_to(python)
    receipt = evidence.load(execution['receipt'])
    receipt['command'][0] = str(alias)
    execution['receipt'] = reference(directory / 'alias-receipt.json', json.dumps(receipt).encode())
    execution_ref = reference(directory / 'alias-execution.json', json.dumps(execution).encode())
    summary['execution'] = manifest['execution'] = execution_ref
    manifest['external_evidence'] = {execution['receipt']['path']: execution['receipt']['sha256']}
    manifest_ref = reference(directory / 'alias-manifest.json', json.dumps(manifest).encode())
    summary['readonly_final']['manifest_sha256'] = manifest_ref['sha256']
    evidence.validate_fresh_c9(summary, execution_ref, manifest_ref, snapshot_ref, repo=repo)
    alias.unlink()
    alias.write_text('different interpreter')
    with pytest.raises(ValueError, match='registered Python'):
        evidence.validate_fresh_c9(summary, execution_ref, manifest_ref, snapshot_ref, repo=repo)


def test_original_directory_is_bound_before_loading_or_environment_install(tmp_path):
    """SYNTHETIC FORMAT closure, including constructor and policy files."""
    directory = tmp_path / 'registered-original'
    directory.mkdir()
    field_names = {'resource': 'resource.json', 'authority': 'authority.json', 'build': 'build.json',
        'build_config': 'config.json', 'prepared': 'prepared.json', 'switch_environment': 'switch-environment.json',
        'chain': 'c9-evidence.json', 'd4_model': 'd4-model.json', 'd5_model': 'd5-model.json',
        'attempt': 'live-attempt.json', 'switch': 'build-and-switch.json', 'session': 'session.json', 'policy': 'policy.json'}
    execution = {key: reference(directory / name, json.dumps({'SYNTHETIC_FORMAT_ONLY': name}).encode()) for key, name in field_names.items()}
    execution['resource'] = reference(directory / 'resource.json', json.dumps(dict(r6_exercise_directory=str(directory))).encode())
    execution['configurations'] = {name: reference(directory / filename, b'{"SYNTHETIC_FORMAT_ONLY":true}')
                                 for name, filename in [('candidate', 'environment.json'), ('compatible', 'environment.compat.json')]}
    captured = evidence.verified_original_files(execution, directory)
    assert captured['resource.json']['r6_exercise_directory'] == str(directory)
    alternate = tmp_path / 'selfsigned-alternate'
    alternate.mkdir()
    for path in directory.iterdir():
        (alternate / path.name).write_bytes(path.read_bytes())
    with pytest.raises(ValueError):
        evidence.verified_original_files(execution, alternate)
    original = execution['configurations']['candidate']
    execution['configurations']['candidate'] = reference(alternate / 'environment.json', b'{"selfsigned_alternate":true}')
    with pytest.raises(ValueError):
        evidence.verified_original_files(execution, directory)
    execution['configurations']['candidate'] = original
    (directory / 'session.json').write_text('{"changed_constructor_data":true}')
    with pytest.raises(ValueError):
        evidence.verified_original_files(execution, directory)


def test_recorded_execution_commit_survives_only_document_content_changes(tmp_path, monkeypatch):
    import subprocess
    values, candidate, configurations, execution, repo = synthetic_provenance(tmp_path, monkeypatch)
    evidence.validate_provenance(values, candidate, configurations, execution, repo=repo)
    (repo / 'README.md').write_text('SYNTHETIC FORMAT documentation-only follow-up')
    subprocess.run(['git', 'add', 'README.md'], cwd=repo, check=True)
    subprocess.run(['git', '-c', 'user.name=Synthetic Format', '-c', 'user.email=synthetic@invalid',
                    'commit', '-qm', 'SYNTHETIC docs-only'], cwd=repo, check=True)
    # Original stock/property/build SHA is preserved, never rewritten to this HEAD.
    evidence.validate_provenance(values, candidate, configurations, execution, repo=repo)
    (repo / 'backend/tests/e2e/r6_exercise.py').write_text('changed execution source')
    with pytest.raises(ValueError):
        evidence.validate_provenance(values, candidate, configurations, execution, repo=repo)


def test_valid_proof_cannot_select_an_alternate_selfsigned_original_before_compile(tmp_path, monkeypatch):
    import os
    summary, execution_ref, manifest_ref, snapshot_ref, repo = synthetic_full_execution(tmp_path, monkeypatch)
    execution = evidence.load(execution_ref)
    original = Path(execution['resource']['path']).parent
    evidence.validate_fresh_c9(summary, execution_ref, manifest_ref, snapshot_ref, repo=repo)
    evidence.verified_original_files(execution, original)  # Valid proof/directory positive control.
    alternate = tmp_path / 'selfsigned-alternate-original'
    alternate.mkdir()
    (alternate / 'authority.json').write_text('{"selfsigned":"untrusted"}')
    (alternate / 'environment.json').write_text('{"untrusted_env":"must_not_install"}')
    expected_environment = dict(os.environ)
    entered = []
    original_validator = evidence.validate_fresh_c9
    def validated(*args, **kwargs):
        return original_validator(*args, **kwargs, repo=repo)
    monkeypatch.setattr(evidence, 'validate_fresh_c9', validated)
    # A final-source reader can only reach this after the original path is bound.
    real_bytes = evidence.registered_verifier_bytes
    def observed(*args, **kwargs):
        # validate_fresh_c9 checks registered bytes without execution once. The
        # second loader entry would only occur after directory authentication.
        entered.append(True)
        return real_bytes(*args, **kwargs)
    monkeypatch.setattr(evidence, 'registered_verifier_bytes', observed)
    with pytest.raises(ValueError, match='trusted resource parent'):
        evidence.trusted_readonly_verifier(summary, execution_ref, manifest_ref, snapshot_ref,
            evidence.load(manifest_ref)['readonly_verifier'], original=alternate)
    assert len(entered) == 1
    assert dict(os.environ) == expected_environment


@pytest.mark.parametrize('change', ('added', 'deleted', 'untracked', 'blob', 'mode', 'symlink', 'wrong_commit_with_reverted_worktree', 'staged'))
def test_recorded_git_tree_rejects_non_document_source_drift(tmp_path, monkeypatch, change):
    import subprocess
    values, candidate, configurations, execution, repo = synthetic_provenance(tmp_path, monkeypatch)
    path = repo / 'backend/tests/e2e/r6_exercise.py'
    before = path.read_bytes()
    if change == 'added':
        (repo / 'added.py').write_text('SYNTHETIC extra code')
        subprocess.run(['git', 'add', 'added.py'], cwd=repo, check=True)
    elif change == 'deleted': path.unlink()
    elif change == 'untracked': (repo / 'untracked.py').write_text('SYNTHETIC unknown source')
    elif change == 'blob': values['source_manifest']['files']['backend/tests/e2e/r6_exercise.py'] = '0' * 64
    elif change == 'mode': path.chmod(0o755)
    elif change == 'symlink':
        target = tmp_path / 'external-source.py'
        target.write_bytes(before)
        path.unlink()
        path.symlink_to(target)
    else:
        path.write_text('SYNTHETIC different committed code')
        subprocess.run(['git', 'add', str(path.relative_to(repo))], cwd=repo, check=True)
        if change == 'wrong_commit_with_reverted_worktree':
            subprocess.run(['git', '-c', 'user.name=Synthetic Format', '-c', 'user.email=synthetic@invalid',
                            'commit', '-qm', 'SYNTHETIC changed source'], cwd=repo, check=True)
        path.write_bytes(before)
    with pytest.raises(ValueError):
        evidence.validate_provenance(values, candidate, configurations, execution, repo=repo)


def test_actual_profile_audits_allow_opaque_turn_but_reject_body_or_schema_drift():
    from copy import deepcopy
    original = synthetic_chain()
    rows = original[0]['database']['audit']
    d5_attempt, d5_completed = rows[2], rows[3]
    d5_attempt['changed_fields']['snapshot_hmac'] = None  # Actual initial opaque-only turn.
    delivered_attempt, delivered_completed = deepcopy(d5_attempt), deepcopy(d5_completed)
    delivered_attempt['log_id'] = '00000000-0000-0000-0000-000000000070'
    delivered_attempt['changed_fields']['snapshot_hmac'] = 'a' * 64
    delivered_completed['log_id'] = '00000000-0000-0000-0000-000000000071'
    delivered_completed['correlation_id'] = delivered_attempt['log_id']
    rows.extend([delivered_attempt, delivered_completed])
    evidence.validate_chain(*original)
    for change in ('d4_version', 'd4_snapshot', 'd4_run_correlation', 'd5_missing_version', 'd5_wrong_run',
                   'all_opaque', 'malformed_snapshot', 'top_body', 'metadata_body', 'old_body', 'new_body',
                   'duplicate_id', 'failed_model', 'timestamp_body'):
        args = deepcopy(original)
        audit = args[0]['database']['audit']
        if change == 'd4_version': audit[0]['changed_fields']['version'] = 'unexpected'
        elif change == 'd4_snapshot': audit[0]['changed_fields']['snapshot_hmac'] = 'a' * 64
        elif change == 'd4_run_correlation': audit[0]['correlation_id'] = audit[0]['changed_fields']['run_id']
        elif change == 'd5_missing_version': audit[2]['changed_fields'].pop('version')
        elif change == 'd5_wrong_run': audit[2]['correlation_id'] = audit[0]['changed_fields']['run_id']
        elif change == 'all_opaque': audit[4]['changed_fields']['snapshot_hmac'] = None
        elif change == 'malformed_snapshot': audit[4]['changed_fields']['snapshot_hmac'] = 'business body'
        elif change == 'top_body': audit[0]['prompt'] = 'forbidden body'
        elif change == 'metadata_body': audit[0]['user_agent'] = 'forbidden body'
        elif change == 'old_body': audit[0]['old_values'] = {'body': 'forbidden'}
        elif change == 'new_body': audit[0]['new_values'] = {'body': 'forbidden'}
        elif change == 'duplicate_id': audit[5]['log_id'] = audit[3]['log_id']
        elif change == 'failed_model': audit.append(dict(audit[0], action='MODEL_EGRESS_FAILED'))
        elif change == 'timestamp_body': audit[0]['operated_at'] = 'forbidden body'
        with pytest.raises(ValueError):
            evidence.validate_chain(*args)


@pytest.mark.parametrize('profile', ('d4', 'd5'))
@pytest.mark.parametrize('change', ('missing', 'wrong', 'duplicate'))
def test_each_profile_requires_exact_actual_completion_to_attempt_bijection(profile, change):
    from copy import deepcopy
    args = synthetic_chain()
    rows = args[0]['database']['audit']
    index = 1 if profile == 'd4' else 3
    if change == 'missing': rows.pop(index)
    elif change == 'wrong': rows[index]['correlation_id'] = '00000000-0000-0000-0000-000000000099'
    else: rows.append(deepcopy(rows[index]))
    with pytest.raises(ValueError):
        evidence.validate_chain(*args)


def enrich_input_receipts(values):
    """SYNTHETIC FORMAT fields matching the actual typed input-receipt schema."""
    chain = values['chain']
    origins = [row['body'] for row in chain['database']['capa_r6_source_origins']]
    for index, row in enumerate(origins):
        row.update(source_id=f'00000000-0000-0000-0000-{80 + index:012d}', kind='report_snapshot' if index < 2 else 'fmea_projection',
                   version=str(index + 1), source_version_counter=index + 1, snapshot_id=None, fmea_id=None,
                   node_id=None, factory_id=values['session']['factory_id'], product_line_code='SYNTHETIC_FORMAT_ONLY')
    fields = ('kind', 'projection_id', 'version', 'source_version_counter', 'snapshot_id', 'fmea_id', 'node_id', 'factory_id', 'product_line_code')
    run = next(run for run in values['models']['runs'] if run['task_id'] == chain['d4_task'])
    run['lease_epoch'] = 2
    chain['database']['agent_d4_input_receipts'] = [dict(body=dict(receipt_id='00000000-0000-0000-0000-000000000090',
        report_id=chain['report_id'], task_id=chain['d4_task'], run_id=run['run_id'], lease_epoch=1,
        tenant_generation=values['session']['generation'], executor_id=values['session']['actors']['qe']['user_id'],
        installation_id=values['prepared']['d4']['installation_id'], deployment_id=values['models']['d4']['deployment_id'],
        deployment_config_hmac=values['models']['d4']['config_hmac'], source_count=3,
        input_versions={row['source_id']: {key: row[key] for key in fields} for row in origins}))]


@pytest.mark.parametrize('change', ('task', 'run', 'installation', 'deployment', 'model_hmac', 'executor', 'generation',
                                   'lease', 'source_count', 'source_version', 'duplicate', 'full_db_actor'))
def test_input_receipt_crossbinding_rejects_other_same_report_evidence(tmp_path, monkeypatch, change):
    from copy import deepcopy
    proof = synthetic_full_execution(tmp_path, monkeypatch)
    execution = evidence.load(proof[1])
    values = {name: evidence.load(execution[name]) for name in ('chain', 'models', 'session', 'prepared')}
    snapshot = evidence.load(proof[3])
    evidence.validate_d4_input_receipts(values, snapshot)
    row = values['chain']['database']['agent_d4_input_receipts'][0]['body']
    if change == 'task': row['task_id'] = values['chain']['d5_task']
    elif change == 'run': row['run_id'] = next(run['run_id'] for run in values['models']['runs'] if run['task_id'] == values['chain']['d5_task'])
    elif change == 'installation': row['installation_id'] = values['prepared']['d5']['installation_id']
    elif change == 'deployment': row['deployment_id'] = values['models']['d5']['deployment_id']
    elif change == 'model_hmac': row['deployment_config_hmac'] = '0' * 64
    elif change == 'executor': row['executor_id'] = '00000000-0000-0000-0000-000000000099'
    elif change == 'generation': row['tenant_generation'] += 1
    elif change == 'lease': row['lease_epoch'] = 3
    elif change == 'source_count': row['source_count'] = True
    elif change == 'source_version': next(iter(row['input_versions'].values()))['version'] = 'another-version'
    elif change == 'duplicate': values['chain']['database']['agent_d4_input_receipts'].append(deepcopy(values['chain']['database']['agent_d4_input_receipts'][0]))
    elif change == 'full_db_actor': snapshot['immutable_original_model']['agent_tasks'][0]['executor_user_id'] = '00000000-0000-0000-0000-000000000099'
    with pytest.raises(ValueError):
        evidence.validate_d4_input_receipts(values, snapshot)


def test_checker_uses_original_independent_anchor_and_restores_runtime_environment(monkeypatch):
    import os
    monkeypatch.setenv('R6_SWITCH_AUTHORITY_FILE', '/synthetic/original-authority.json')
    monkeypatch.setenv('R6_SWITCH_AUTHORITY_KEY', 'synthetic-original-independent-key')
    monkeypatch.setenv('OPENQMS_GATE_HOOKS', '/synthetic/stock-hooks.json')
    caller = dict(os.environ)
    monkeypatch.setenv('R6_SWITCH_AUTHORITY_FILE', '/synthetic/compatible/authority.json')
    monkeypatch.setenv('R6_GENERATION_ENABLED', 'false')
    runtime = dict(os.environ)
    with pytest.raises(RuntimeError, match='synthetic checker exception'):
        with evidence.checker_environment(caller):
            assert dict(os.environ) == caller
            raise RuntimeError('synthetic checker exception')
    assert dict(os.environ) == runtime
    assert os.environ['OPENQMS_GATE_HOOKS'] == '/synthetic/stock-hooks.json'


def test_readonly_verification_projection_removes_only_create_transient():
    from copy import deepcopy
    chain = synthetic_chain()[0]
    snapshot = dict(report_id=chain['report_id'], measure_id=chain['measure_id'], a=chain['a'], b=chain['b'],
        current=dict(status='D8_CLOSURE'), original_switch=chain['switch'], history=chain['history'], review=chain['review'],
        database=deepcopy(chain['database']), verification=[{k: v for k, v in chain['verification'].items() if k != 'source_proof_issued'}])
    evidence.validate_readonly_material(chain, snapshot)
    snapshot['verification'][0]['unexpected_field'] = 'must not be ignored'
    with pytest.raises(ValueError): evidence.validate_readonly_material(chain, snapshot)
    snapshot['verification'][0].pop('unexpected_field')
    chain['verification']['unexpected_create_field'] = 'must not be dropped'
    with pytest.raises(ValueError): evidence.validate_readonly_material(chain, snapshot)


@pytest.mark.asyncio
async def test_entire_checker_caller_environment_restores_on_pre_setup_exception(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv('OPENQMS_GATE_HOOKS', '/synthetic/original-hooks.json')
    before, directory = dict(os.environ), Path.cwd()
    @evidence.preserve_caller_environment
    async def before_setup():
        os.environ.clear()
        os.environ['selfsigned_untrusted_context'] = 'must disappear'
        os.chdir(tmp_path)
        raise ValueError('synthetic pre-setup failure')
    with pytest.raises(ValueError, match='pre-setup'):
        await before_setup()
    assert dict(os.environ) == before
    assert Path.cwd() == directory


def test_pure_material_checks_preserve_controlled_classification_and_cannot_qualify_live():
    args = synthetic_chain()
    args[0]['live_provider'] = False
    before = json.dumps(args[0], sort_keys=True)
    ids = evidence.validate_chain_material(args[0], args[1], args[2], args[3], args[4])
    assert ids['report_id'] == args[0]['report_id']
    assert args[0]['live_provider'] is False
    assert json.dumps(args[0], sort_keys=True) == before
    with pytest.raises(ValueError, match='not genuine cloud'):
        evidence.validate_chain(*args)
