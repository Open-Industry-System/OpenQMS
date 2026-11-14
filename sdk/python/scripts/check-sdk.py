"""Offline SDK developer gates, not production or fixed-worker admission.

Only safe status/path output is public. Child output is discarded; receipts and
fixed-count filtered logs live in unique private artifact directories.
"""
import argparse
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time

SDK = Path(__file__).resolve().parents[1]
COUNTERS = ('selected', 'passed', 'failed', 'errors', 'skipped', 'xfailed',
            'xpassed', 'deselected', 'warnings')


def artifact_directory(parent):
    parent = Path(parent).absolute()
    if any(p.is_symlink() for p in (parent, *parent.parents)):
        raise ValueError('unsafe_artifact_path')
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix='sdk-check-', dir=parent))


def private_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        path.chmod(0o600)
        json.dump(value, stream, sort_keys=True, indent=2)


def environment(workspace):
    for name in ('home', 'tmp'):
        (workspace / name).mkdir(mode=0o700, exist_ok=True)
    return {'PATH': str(Path(sys.executable).absolute().parent) + os.pathsep + os.defpath,
            'HOME': str(workspace / 'home'), 'TMPDIR': str(workspace / 'tmp'),
            'PIP_CONFIG_FILE': os.devnull, 'PIP_NO_INDEX': '1', 'PIP_NO_CACHE_DIR': '1',
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONNOUSERSITE': '1', 'LANG': 'C.UTF-8'}


def pytest_passed(result):
    return (all(type(result.get(k)) is int and result[k] >= 0 for k in COUNTERS)
            and result.get('exit') == 0 and result['selected'] > 0
            and result['passed'] == result['selected']
            and not any(result[k] for k in ('failed', 'errors', 'skipped', 'xfailed', 'xpassed')))


def execute(command, workspace, env, *, timeout=300):
    # No portable tree termination guarantee outside POSIX: do not launch there.
    if os.name != 'posix':
        return 125
    child = None
    try:
        child = subprocess.Popen(command, cwd=workspace / 'home', env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        # Popen successfully created OUR new session: pid is its original PGID.
        # Never derive a target from caller input or from the caller's group.
        group = child.pid
        return child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124
    except OSError:
        return 125
    finally:
        if child is not None:
            # Also clean up when the leader exited before its descendants.
            try:
                os.killpg(group, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            finally:
                # Give orphaned descendants a bounded TERM grace too: wait()
                # alone returns immediately when the leader has already exited.
                deadline = time.monotonic() + 0.2
                while time.monotonic() < deadline:
                    try:
                        os.killpg(group, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.01)
                # Descendants can ignore TERM even if the leader already exited.
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()


def pytest_layer(layer, workspace, env):
    receipt = workspace / f'{layer}-pytest.json'
    if layer == 'unit':
        command = [sys.executable, '-I', '-B', str(SDK / 'scripts' / 'check-sdk-pure.py'),
                   '--receipt', str(receipt)]
    else:
        loader = ("import importlib.util; s=importlib.util.spec_from_file_location('sdk_pytest', "
                  + repr(str(SDK / 'scripts' / 'check-sdk-pure.py'))
                  + "); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                  + "raise SystemExit(m.run_pytest('loopback', " + repr(str(receipt)) + "))")
        command = [sys.executable, '-I', '-B', '-c', loader]
    started = time.monotonic()
    code = execute(command, workspace, env)
    result = dict.fromkeys(COUNTERS, 0)
    result.update(exit=code, elapsed=time.monotonic() - started, layer=layer,
                  pure=(layer == 'unit'), status='FAIL')
    try:
        child = json.loads(receipt.read_text(encoding='utf-8'))
        if (isinstance(child, dict) and child.get('layer') == layer
                and child.get('pure') is (layer == 'unit')
                and child.get('exit') == code):
            result.update({k: child[k] for k in (*COUNTERS, 'elapsed')})
            if pytest_passed(result):
                result['status'] = 'PASS'
    except (OSError, ValueError, KeyError, TypeError):
        result['diagnostic'] = 'missing_or_invalid_receipt'
    result['child_receipt'] = str(receipt)
    return result


# Executes only from a fresh venv, isolated mode, outside the repository.
PROBE = r'''
from importlib import metadata, util
from pathlib import Path
import json, sys
# Python-level audit only; not an OS/native-code sandbox.
def deny(event, args):
    if event.startswith('socket.'):
        raise RuntimeError('probe_network_denied')
sys.addaudithook(deny)
import openqms_agent_sdk as sdk
root = Path(sys.prefix).resolve()
module = Path(sdk.__file__).resolve()
assert module.is_relative_to(root) and 'site-packages' in module.parts
info = metadata.metadata('openqms-agent-sdk')
assert info['Version'] == sdk.__version__ == '0.1.0'
assert info['Requires-Python'] == '>=3.11'
assert not info.get_all('Requires-Dist')
for name in ('app', 'fastapi', 'pydantic_settings', 'pydantic', 'sqlalchemy', 'jose',
             'openai', 'anthropic', 'httpx', 'requests'):
    assert util.find_spec(name) is None
expected = {'__version__', 'SDKError', 'ConfigError', 'ValidationError', 'TransportError',
 'RequestTimeout', 'HTTPError', 'ProtocolError', 'ResponseTooLarge', 'UnknownOutcome',
 'ClientClosed', 'ClientBusy', 'ClientConfig', 'RunClaim', 'Capability', 'Capabilities',
 'RuntimeMessage', 'MessageBatch', 'MessageAck', 'MessageHistory', 'Verification',
 'CapaContext', 'EventPayload', 'ResultPayload', 'Source', 'RuntimeEvent', 'RuntimeResult',
 'ReadonlyCheckpoint', 'FinishResult', 'InstallationClient', 'RunClient'}
assert set(sdk.__all__) == expected and len(sdk.__all__) == len(expected)
for name in ('ClaimEnvelope', 'EncodedRequest', 'WireResponse', 'SUPPORTED_OPERATIONS'):
    assert not hasattr(sdk, name)
for cls in (sdk.InstallationClient, sdk.RunClient):
    for name in ('get', 'post', 'request', 'renew', 'reopen', 'load_checkpoint'):
        assert not hasattr(cls, name)
assert callable(sdk.InstallationClient.claim_run)
for name in ('capabilities', 'claim_messages', 'ack_messages', 'get_capa_context',
             'record_event', 'save_result', 'save_checkpoint', 'message_history', 'finish'):
    assert callable(getattr(sdk.RunClient, name))
# Construction/close must also remain local under the import-time guard.
client = sdk.InstallationClient(sdk.ClientConfig('http://127.0.0.1:1', 'fixture'),
    '00000000-0000-0000-0000-000000000001', 'fixture-only-not-a-credential')
client.close()
with open(sys.argv[1], 'x', encoding='utf-8') as stream:
    json.dump({'version': sdk.__version__, 'module': str(module), 'api_methods': 10,
               'runtime_requirements': [], 'status': 'PASS'}, stream)
'''


# Invoke the existing builder CLI contract under execute's owned process group.
# Its stdout is JSON metadata only, bounded before allocation/writing; raw errors
# remain on discarded stderr. No builder interface or runtime API is changed.
BUILD_METADATA = r'''
import contextlib, importlib.util, io, json, os, sys
class BoundedJSON(io.StringIO):
    def write(self, text):
        if self.tell() + len(text) > 65536:
            raise ValueError('metadata_too_large')
        return super().write(text)
spec = importlib.util.spec_from_file_location('wheel_cli', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output = BoundedJSON()
with contextlib.redirect_stdout(output):
    code = module.main(['--source', sys.argv[2], '--artifacts', sys.argv[3]])
if code:
    raise SystemExit(code)
metadata = json.loads(output.getvalue())
with open(sys.argv[4], 'x', encoding='utf-8') as stream:
    os.chmod(sys.argv[4], 0o600)
    json.dump(metadata, stream, sort_keys=True)
'''


def wheel_layer(workspace, env):
    started = time.monotonic()
    result = dict.fromkeys(COUNTERS, 0)
    result.update(layer='wheel', pure=False, status='FAIL', exit=1)
    try:
        metadata_path = workspace / 'wheel-build.json'
        code = execute([sys.executable, '-I', '-B', '-c', BUILD_METADATA,
                        str(SDK / 'scripts' / 'build-wheel.py'), str(SDK),
                        str(workspace), str(metadata_path)], workspace, env, timeout=180)
        result['build_exit'] = code
        if code != 0 or metadata_path.stat().st_size > 65536:
            raise ValueError('build_failed')
        built = json.loads(metadata_path.read_text(encoding='utf-8'))
        result.update(built)
        target = workspace / 'installation'
        # ensurepip uses only Python's bundled wheels, never the network.
        code = execute([sys.executable, '-I', '-B', '-m', 'venv', str(target)], workspace, env, timeout=120)
        result['venv_exit'] = code
        if code != 0:
            raise ValueError('venv_failed')
        python = target / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        code = execute([str(python), '-I', '-B', '-m', 'pip', '--isolated',
                        '--disable-pip-version-check', 'install', '--no-index', '--no-deps',
                        built['wheel_path']], workspace, env, timeout=120)
        result['install_exit'] = code
        if code != 0:
            raise ValueError('install_failed')
        probe_path = workspace / 'wheel-probe.json'
        code = execute([str(python), '-I', '-B', '-c', PROBE, str(probe_path)], workspace, env, timeout=30)
        result['probe_exit'] = code
        result['exit'] = code
        result['selected'] = 1  # one actual isolated installation probe, not pytest
        result['count_kind'] = 'isolated_wheel_probe'
        if code == 0:
            probe = json.loads(probe_path.read_text(encoding='utf-8'))
            if probe.get('status') != 'PASS' or probe.get('api_methods') != 10:
                raise ValueError('invalid_probe_receipt')
            probe_path.chmod(0o600)
            result.update(status='PASS', passed=1, probe=probe)
        else:
            result['failed'] = 1
    except Exception:
        # Never expose exception text, builder stdout or paths from diagnostics.
        result.update(status='FAIL', errors=1)
        if result['exit'] == 0:
            result['exit'] = 1
        result['diagnostic'] = 'wheel_check_failed'
    result['elapsed'] = time.monotonic() - started
    return result


def source_identity(env, workspace):
    commit = subprocess.run(['git', '-C', str(SDK), 'rev-parse', 'HEAD'],
        cwd=workspace / 'home', env=env, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=10, check=False)
    if commit.returncode != 0:
        raise ValueError('source_identity_failed')
    manifest = {}
    for path in sorted(SDK.rglob('*')):
        if path.is_file() and not path.is_symlink() and (path.suffix == '.py' or path.name in ('README.md', 'pyproject.toml')):
            manifest[path.relative_to(SDK).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'source_commit': commit.stdout.decode('ascii').strip(), 'gate_source_manifest': manifest,
            'source_hash': hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'invalid_arguments\n')


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('--layer', choices=('unit', 'loopback', 'wheel', 'all'), default='all')
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        workspace = artifact_directory(args.artifacts)
        env = environment(workspace)
        identity = source_identity(env, workspace)
        results = []
        for layer in (('unit', 'loopback', 'wheel') if args.layer == 'all' else (args.layer,)):
            result = wheel_layer(workspace, env) if layer == 'wheel' else pytest_layer(layer, workspace, env)
            result.update(identity)
            # Verify the exact gate inputs stayed frozen for the entire layer.
            if source_identity(env, workspace) != identity:
                result.update(status='FAIL', diagnostic='source_changed')
            private_json(workspace / f'{layer}-receipt.json', result)
            log = workspace / f'{layer}-filtered.log'
            with log.open('x', encoding='utf-8') as stream:
                log.chmod(0o600)
                stream.write(json.dumps({k: result[k] for k in (*COUNTERS, 'exit', 'elapsed', 'status')}) + '\n')
            results.append(result)
            print(f'{layer}: {result["status"]} {workspace / (layer + "-receipt.json")}')
        private_json(workspace / 'summary.json', {'layers': results, **identity})
        return 0 if all(r['status'] == 'PASS' for r in results) else 1
    except Exception:
        print('sdk-check: FAIL', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
