from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

from tests.ci.gate_results import COUNTS

SHA = 'a' * 40
OBSERVATIONS = ('versioncommands', 'eicar_reply', 'parse_trace', 'malware_rejection',
                'encrypted_pdf', 'expansion_limit', 'clean_download')


def receipt(layer='live', stage=None):
    result = dict(layer=layer, frozen_sha=SHA, command=['python', '-m', 'pytest'],
                  status='PASSED', exit_code=0, elapsed_seconds=1.2,
                  **dict.fromkeys(COUNTS, 0))
    result.update(selected=1, passed=1)
    if stage:
        result['stage'] = stage
    if stage == 'process':
        result['observations'] = dict.fromkeys(OBSERVATIONS, 'actual safe observation')
    return result


def write_pair(root, payload):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'actual-receipt.json').write_text(json.dumps(payload))
    (root / 'actual.log').write_text('actual selected pytest diagnostic\n')


@pytest.mark.parametrize('code', [0, 1])
def test_real_child_receipt_log_counts_sha_and_failures_are_retained(tmp_path, capsys, code):
    from tests.e2e.capa_outcome_runner import run_pytest_layer

    child = tmp_path / 'test_child.py'
    child.write_text('def test_child():\n    print("actual-safe-diagnostic")\n    assert ' + str(code == 0) + '\n')
    artifacts = tmp_path / 'safe'
    artifacts.mkdir()
    root = Path(__file__).resolve().parents[3]
    result = run_pytest_layer(
        layer='api', targets=[str(child)], source={'PATH': os.environ['PATH'], 'OPENQMS_CI_SHA': SHA},
        database_url='postgresql+asyncpg://u:synthetic-password@127.0.0.1:1/qms_test',
        artifacts=artifacts, python=sys.executable,
        pytest_entrypoint=(str(root / 'scripts/check-ci-pure.py'),),
    )
    assert result['frozen_sha'] == SHA
    assert result['exit_code'] == code
    assert result['selected'] == 1
    assert result['failed'] == code
    assert result['status'] == ('PASSED' if code == 0 else 'FAILED')
    assert json.loads(next(artifacts.glob('*-receipt.json')).read_text()) == result
    assert 'actual-safe-diagnostic' in next(artifacts.glob('*.log')).read_text()
    output = capsys.readouterr().out
    assert 'selected' in output and 'exit_code' in output
    if code:
        assert 'actual-safe-diagnostic' in output and 'assert False' in output
    assert {p.suffix for p in artifacts.iterdir()} == {'.json', '.log'}


def test_scanner_export_preserves_actual_files_after_volume_deleted_and_is_host_readable(tmp_path):
    from tests.ci.acceptance_evidence import export_scanner_evidence

    volume = tmp_path / 'volume'
    write_pair(volume, receipt('scanner', 'process'))
    # Raw/private siblings are not part of the safe export, even if accidentally present.
    for name in ('raw.xml', 'result.hooks.json', '.env', 'profile.txt', 'registry.json'):
        (volume / name).write_text('synthetic-private-do-not-publish')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for path in volume.iterdir():
            path.chmod(0o600)
            archive.add(path, arcname=path.name)
    exported = tmp_path / 'host-safe'
    export_scanner_evidence(io.BytesIO(stream.getvalue()), exported)
    shutil.rmtree(volume)  # model the owned Docker volume teardown, not a mocked filename check
    payload = json.loads((exported / 'actual-receipt.json').read_text())
    assert payload == receipt('scanner', 'process')
    assert (exported / 'actual.log').read_text() == 'actual selected pytest diagnostic\n'
    assert all(p.stat().st_mode & 0o444 == 0o444 for p in exported.iterdir())
    assert set(p.name for p in exported.iterdir()) == {'actual-receipt.json', 'actual.log'}


def test_scanner_export_does_not_follow_tar_links_or_paths(tmp_path):
    from tests.ci.acceptance_evidence import export_scanner_evidence

    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        member = tarfile.TarInfo('../escape.log')
        member.size = 4
        archive.addfile(member, io.BytesIO(b'nope'))
        member = tarfile.TarInfo('linked.log')
        member.type = tarfile.SYMTYPE
        member.linkname = '/etc/passwd'
        archive.addfile(member)
    with pytest.raises(ValueError):
        export_scanner_evidence(io.BytesIO(stream.getvalue()), tmp_path / 'safe')
    assert not (tmp_path / 'escape.log').exists()


@pytest.mark.parametrize('mutation', ['wrapper', 'sha', 'missing_log', 'empty_log', 'nonzero', 'skip', 'zero', 'missing_count', 'mismatch'])
def test_summary_rejects_status_wrappers_and_incomplete_or_wrong_source_receipts(tmp_path, mutation):
    from tests.ci.acceptance_evidence import summarize_acceptance

    payload = receipt()
    if mutation == 'wrapper':
        payload = {'gate': 'live-capa', 'status': 'PASSED'}
    elif mutation == 'sha':
        payload['frozen_sha'] = 'b' * 40
    elif mutation == 'nonzero':
        payload['exit_code'] = 1
    elif mutation == 'skip':
        payload['skipped'] = 1
    elif mutation == 'zero':
        payload.update(selected=0, passed=0)
    elif mutation == 'missing_count':
        del payload['warnings']
    elif mutation == 'mismatch':
        payload['passed'] = 0
    write_pair(tmp_path / 'live-capa', payload)
    if mutation == 'missing_log':
        (tmp_path / 'live-capa/actual.log').unlink()
    if mutation == 'empty_log':
        (tmp_path / 'live-capa/actual.log').write_text('')
    with pytest.raises(ValueError):
        summarize_acceptance(tmp_path, 'live-capa', SHA, {'live-capa': 'success', 'scanner': 'skipped'})


def test_summary_requires_both_scanner_stages_metadata_and_actual_cleanup(tmp_path):
    from tests.ci.acceptance_evidence import summarize_acceptance, write_cleanup

    write_pair(tmp_path / 'scanner/process', receipt('scanner', 'process'))
    write_pair(tmp_path / 'scanner/browser', receipt('scanner', 'browser'))
    results = {'scanner': 'success', 'live-capa': 'skipped'}
    with pytest.raises(ValueError):
        summarize_acceptance(tmp_path, 'scanner', SHA, results)
    write_cleanup(tmp_path / 'scanner', SHA, 'owned-project', 0, '', '', '', 0)
    assert summarize_acceptance(tmp_path, 'scanner', SHA, results) == {
        'scanner': 'PASSED', 'live-capa': 'NOT_REQUESTED', 'frozen_sha': SHA,
    }
    payload = receipt('scanner', 'process')
    del payload['observations']['versioncommands']
    write_pair(tmp_path / 'scanner/process', payload)
    with pytest.raises(ValueError):
        summarize_acceptance(tmp_path, 'scanner', SHA, results)


def test_summary_live_requires_actual_counts_and_marks_unrequested_gate(tmp_path):
    from tests.ci.acceptance_evidence import summarize_acceptance

    write_pair(tmp_path / 'live-capa', receipt())
    assert summarize_acceptance(tmp_path, 'live-capa', SHA, {'live-capa': 'success', 'scanner': 'skipped'}) == {
        'live-capa': 'PASSED', 'scanner': 'NOT_REQUESTED', 'frozen_sha': SHA,
    }
    with pytest.raises(ValueError):
        summarize_acceptance(tmp_path, 'live-capa', SHA, {'live-capa': 'failure', 'scanner': 'skipped'})


def test_scanner_observations_are_extracted_without_private_junit_or_unknown_properties(tmp_path):
    from tests.e2e.capa_outcome_runner import run_pytest_layer

    child = tmp_path / 'test_observed.py'
    child.write_text('import pytest\n@pytest.mark.real_scanner\ndef test_actual(record_property):\n'
                     '    record_property("versioncommands", "ClamAV 1.4.3/definitions | INSTREAM")\n'
                     '    record_property("unreviewed", "private-do-not-publish")\n')
    artifacts = tmp_path / 'safe'
    artifacts.mkdir()
    root = Path(__file__).resolve().parents[3]
    result = run_pytest_layer(
        layer='scanner', targets=[str(child)], source={'OPENQMS_CI_SHA': SHA},
        database_url='postgresql+asyncpg://u:p@127.0.0.1:1/qms_test', artifacts=artifacts,
        pytest_entrypoint=(str(root / 'scripts/check-ci-pure.py'),),
    )
    assert result['observations'] == {'versioncommands': 'ClamAV 1.4.3/definitions | INSTREAM'}
    assert not list(artifacts.glob('*.xml'))


@pytest.mark.parametrize('code', [0, 7])
def test_frontend_cli_retains_real_subprocess_exit_and_sanitized_output_without_backend_dependencies(tmp_path, code):
    root = Path(__file__).resolve().parents[3]
    tools = tmp_path / 'tools'
    tools.mkdir()
    for name in ('npx', 'npm'):
        tool = tools / name
        tool.write_text(f'#!/bin/sh\nprintf "actual frontend output synthetic-frontend-key\\n"\nexit {code}\n')
        tool.chmod(0o755)
    safe = tmp_path / 'safe'
    env = {'PATH': str(tools) + os.pathsep + os.defpath, 'PYTHONPATH': str(root / 'backend'),
           'OPENQMS_TEST_ARTIFACTS': str(safe), 'OPENQMS_CI_SHA': SHA,
           'LLM_API_KEY': 'synthetic-frontend-key'}
    completed = subprocess.run([sys.executable, '-S', '-m', 'tests.ci.acceptance_evidence', 'frontend', 'tsc'],
                               cwd=root / 'backend', env=env, text=True, capture_output=True)
    assert completed.returncode == code, completed.stderr
    payload = json.loads((safe / 'frontend-tsc-receipt.json').read_text())
    assert payload['exit_code'] == code
    assert payload['command'] == ['npx', '--no-install', 'tsc', '--noEmit']
    assert payload['frozen_sha'] == SHA
    assert payload['status'] == ('PASSED' if code == 0 else 'FAILED')
    output = (safe / 'frontend-tsc.log').read_text()
    assert 'actual frontend output' in output
    assert 'synthetic-frontend-key' not in output + completed.stdout


@pytest.mark.parametrize('inspection_exit', [0, 1])
def test_cleanup_inspection_errors_cannot_turn_empty_output_into_success(tmp_path, inspection_exit):
    from tests.ci.acceptance_evidence import write_cleanup

    observed = write_cleanup(tmp_path, SHA, 'owned', 0, '', '', '', 0, inspection_exit=inspection_exit)
    assert observed['inspection_exit'] == inspection_exit
    assert observed['status'] == ('FAILED' if inspection_exit else 'PASSED')


def test_summary_cli_without_dependencies_validates_preflight_sha_and_request(tmp_path):
    root = Path(__file__).resolve().parents[3]
    write_pair(tmp_path / 'live-capa', receipt())
    preflight = tmp_path / 'preflight.json'
    preflight.write_text(json.dumps(dict(gate='live-capa', frozen_sha=SHA, status='PASSED')))
    env = {'PYTHONPATH': str(root / 'backend'), 'GATE': 'live-capa', 'FROZEN_SHA': SHA,
           'PREFLIGHT_RESULT': 'success', 'LIVE_RESULT': 'success', 'SCANNER_RESULT': 'skipped'}
    command = [sys.executable, '-S', '-m', 'tests.ci.acceptance_evidence', 'summary', '--root', str(tmp_path)]
    passed = subprocess.run(command, cwd=root / 'backend', env=env, text=True, capture_output=True)
    assert passed.returncode == 0, passed.stderr
    assert json.loads(passed.stdout)['scanner'] == 'NOT_REQUESTED'
    preflight.write_text(json.dumps(dict(gate='scanner', frozen_sha=SHA, status='PASSED')))
    failed = subprocess.run(command, cwd=root / 'backend', env=env, text=True, capture_output=True)
    assert failed.returncode != 0
    assert 'preflight receipt does not match' in failed.stderr


@pytest.mark.parametrize('process_exit', [0, 9])
def test_make_exports_process_receipts_before_owned_teardown_even_when_process_fails(tmp_path, process_exit):
    """Execute the real recipe with local fake Docker transport, never the daemon/DB."""
    root = Path(__file__).resolve().parents[3]
    volume = tmp_path / 'volume'
    payload = receipt('scanner', 'process')
    if process_exit:
        payload.update(status='FAILED', exit_code=process_exit, failed=1, passed=0)
    write_pair(volume, payload)
    archive = tmp_path / 'owned-volume.tar'
    with tarfile.open(archive, 'w') as tar:
        for path in volume.iterdir():
            tar.add(path, arcname=path.name)
    tools = tmp_path / 'tools'
    tools.mkdir()
    events = tmp_path / 'events'
    docker = tools / 'docker'
    docker.write_text(f'#!{sys.executable}\n' + '''import os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['FAKE_EVENTS']).open('a') as events:
    events.write(' '.join(args) + '\\n')
if args[0] == 'cp':
    sys.stdout.buffer.write(Path(os.environ['FAKE_ARCHIVE']).read_bytes())
elif 'down' in args:
    Path(os.environ['FAKE_ARCHIVE']).unlink()
elif 'run' in args:
    raise SystemExit(int(os.environ['FAKE_PROCESS_EXIT']))
''')
    docker.chmod(0o755)
    python = tools / 'controlled-python'
    python.write_text(f'#!{sys.executable}\n' + '''import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if args[:3] == ['-m', 'tests.ci.scanner_gate', 'browser']:
    root = Path(args[args.index('--artifacts') + 1])
    root.mkdir(parents=True)
    payload = json.loads(os.environ['FAKE_BROWSER_RECEIPT'])
    (root / 'actual-receipt.json').write_text(json.dumps(payload))
    (root / 'actual.log').write_text('local fake browser transport, not actual gate evidence\\n')
else:
    os.execv(sys.executable, [sys.executable, *args])
''')
    python.chmod(0o755)
    safe = tmp_path / 'host-safe'
    env = {'PATH': str(tools) + os.pathsep + os.defpath, 'OPENQMS_TEST_ARTIFACTS': str(safe),
           'OPENQMS_CI_SHA': SHA, 'FAKE_ARCHIVE': str(archive), 'FAKE_EVENTS': str(events),
           'FAKE_PROCESS_EXIT': str(process_exit), 'FAKE_BROWSER_RECEIPT': json.dumps(receipt('scanner', 'browser'))}
    completed = subprocess.run(['/usr/bin/make', 'agent-attachment-e2e', 'PYTHON_BIN=' + str(python)],
                               cwd=root, env=env, text=True, capture_output=True)
    assert (completed.returncode == 0) == (process_exit == 0), completed.stdout + completed.stderr
    assert json.loads((safe / 'process/actual-receipt.json').read_text()) == payload
    assert (safe / 'process/actual.log').read_text() == 'actual selected pytest diagnostic\n'
    assert not archive.exists()  # teardown actually deleted the simulated owned volume
    observed = events.read_text()
    assert observed.index('cp ') < observed.index(' down ')
    cleanup = json.loads((safe / 'cleanup.json').read_text())
    assert cleanup['status'] == 'PASSED'  # cleanup and gate success are separate facts
    assert cleanup['inspection_exit'] == cleanup['export_exit'] == cleanup['down_exit'] == 0
    if not process_exit:
        assert (safe / 'browser/actual-receipt.json').is_file()
    else:
        assert not (safe / 'browser').exists()


def test_failed_summary_cli_still_publishes_not_requested_and_actual_failure(tmp_path):
    root = Path(__file__).resolve().parents[3]
    (tmp_path / 'preflight.json').write_text(json.dumps(dict(gate='live-capa', frozen_sha=SHA, status='PASSED')))
    env = {'PYTHONPATH': str(root / 'backend'), 'GATE': 'live-capa', 'FROZEN_SHA': SHA,
           'PREFLIGHT_RESULT': 'success', 'LIVE_RESULT': 'failure', 'SCANNER_RESULT': 'skipped'}
    completed = subprocess.run([sys.executable, '-S', '-m', 'tests.ci.acceptance_evidence', 'summary',
                                '--root', str(tmp_path)], cwd=root / 'backend', env=env, text=True, capture_output=True)
    assert completed.returncode != 0
    published = json.loads((tmp_path / 'summary.json').read_text())
    assert published['live-capa'] == 'FAILED'
    assert published['scanner'] == 'NOT_REQUESTED'
    assert published['frozen_sha'] == SHA
    assert 'failed' in completed.stdout


@pytest.mark.parametrize('field,value', [('command', []), ('elapsed_seconds', None), ('elapsed_seconds', -1)])
def test_summary_requires_actual_command_and_elapsed_receipt(tmp_path, field, value):
    from tests.ci.acceptance_evidence import summarize_acceptance

    payload = receipt()
    payload[field] = value
    write_pair(tmp_path / 'live-capa', payload)
    with pytest.raises(ValueError):
        summarize_acceptance(tmp_path, 'live-capa', SHA, {'live-capa': 'success'})


@pytest.mark.parametrize('password', ['p', 'a'])
def test_short_database_password_does_not_redact_receipt_schema_or_provenance(tmp_path, password):
    from tests.ci.acceptance_evidence import summarize_acceptance
    from tests.e2e.capa_outcome_runner import run_pytest_layer

    root = Path(__file__).resolve().parents[3]
    database_url = f'postgresql+asyncpg://synthetic_user:{password}@127.0.0.1:1/qms_test'
    child = tmp_path / 'test_short_password.py'
    child.write_text('import pytest\n@pytest.mark.live_provider\ndef test_selected_child():\n'
                     f'    print({database_url!r})\n')
    artifacts = tmp_path / 'live-capa'
    artifacts.mkdir()
    actual = run_pytest_layer(
        layer='live', targets=[str(child)], source={'OPENQMS_CI_SHA': SHA},
        database_url=database_url, artifacts=artifacts, python=sys.executable,
        live_configuration={'LLM_PROVIDER': 'openai', 'LLM_MODEL': 'synthetic-model',
                            'LLM_API_KEY': 'synthetic-key'},
        pytest_entrypoint=(str(root / 'scripts/check-ci-pure.py'),),
    )
    assert set(actual) == {'layer', 'command', 'frozen_sha', 'status', 'exit_code', 'elapsed_seconds',
                           'selected', 'passed', 'failed', 'errors', 'skipped', 'xfailed', 'xpassed',
                           'deselected', 'warnings'}
    assert actual['status'] == 'PASSED'
    assert actual['layer'] == 'live'
    assert actual['frozen_sha'] == SHA
    assert actual['selected'] == actual['passed'] == 1
    assert all(type(actual[key]) is int for key in COUNTS)
    assert type(actual['exit_code']) is int and actual['exit_code'] == 0
    assert json.loads(next(artifacts.glob('*-receipt.json')).read_text()) == actual
    assert database_url not in next(artifacts.glob('*.log')).read_text()
    assert summarize_acceptance(tmp_path, 'live-capa', SHA, {'live-capa': 'success'}) == {
        'frozen_sha': SHA, 'live-capa': 'PASSED', 'scanner': 'NOT_REQUESTED',
    }
