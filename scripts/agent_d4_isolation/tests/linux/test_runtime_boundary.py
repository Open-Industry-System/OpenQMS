"""New custom-seccomp matrix. The attack overlay never enters body admission."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import pytest

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[3]


def local_probe():
    path = HERE / 'runtime_boundary_probe.py'
    assert path.is_file(), 'custom-profile boundary probe missing'
    spec = importlib.util.spec_from_file_location('_boundary_local', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def sample(p):
    pre = dict(phase='pre', uid=2001, network={key: 0 for key in p.PRE_NETWORK})
    post = dict(phase='post', uid=2001, network={key: (0 if key == 'api' else p.errno.ETIMEDOUT) for key in p.POST_NETWORK},
                syscalls={key: 1 for key in p.SYSCALLS},
                files=dict(host_file=2, api_file=2, root_write=30, tmp_exec=13),
                mounts={key: True for key in p.MOUNT_FLAGS})
    return pre, post


def test_local_boundary_positive_control_and_complete_post_matrix():
    p = local_probe(); p.validate_results(*sample(p))


@pytest.mark.parametrize('mutation', ['dead_target', 'api_blocked', 'refused_not_dropped',
                                     'syscall_allowed', 'missing_vector', 'attribute_error', 'mount_relaxed'])
def test_local_boundary_rejects_vacuous_or_unproven_denials(mutation):
    p = local_probe(); pre, post = sample(p)
    if mutation == 'dead_target': pre['network']['target'] = 110
    elif mutation == 'api_blocked': post['network']['api'] = 110
    elif mutation == 'refused_not_dropped': post['network']['target'] = p.errno.ECONNREFUSED
    elif mutation == 'syscall_allowed': post['syscalls']['userns'] = 0
    elif mutation == 'missing_vector': post['syscalls'].pop('netlink')
    elif mutation == 'attribute_error': post['syscalls']['ptrace'] = 'AttributeError'
    else: post['mounts']['noexec'] = False
    with pytest.raises(p.BoundaryFailure): p.validate_results(pre, post)


def test_local_boundary_observer_normalizes_only_exact_pinned_entrypoint():
    p = local_probe(); cid = 'c' * 64
    raw = {'Id': cid, 'Image': 'sha256:' + 'e' * 64,
           'Config': {'Entrypoint': ['python', '-c', 'FIXED'], 'User': '2001:2001'},
           'HostConfig': {'Memory': 134217728}}
    class Engine:
        def inspect(self, identity, deadline_ns): return raw
    observer = p.OverlayObserver(Engine(), cid, raw['Image'], ['python', '-c', 'FIXED'])
    result = observer.inspect(cid, 100)
    assert result['Config']['Entrypoint'] == ['python', '-I', '-S', '-B', '/receiver.py']
    assert result['Config']['User'] == raw['Config']['User'] and result['HostConfig'] == raw['HostConfig']
    assert raw['Config']['Entrypoint'] == ['python', '-c', 'FIXED']
    raw['Config']['Entrypoint'] = ['sh']
    with pytest.raises(p.BoundaryFailure): observer.inspect(cid, 100)


def test_local_boundary_cleanup_attempts_every_owned_id(monkeypatch):
    from types import SimpleNamespace
    p = local_probe(); removed = []
    def docker(*args, **kwargs):
        removed.append(args[-1])
        if args[-1] == 'a' * 64: raise OSError('must-not-leak')
    fake = SimpleNamespace(docker=docker, absent=lambda cid: None,
                           inspect=lambda cid: {'Id': cid, 'Image': 'sha256:' + 'e' * 64,
                           'Config': {'Labels': {'org.openqms.d4.boundary.nonce': 'n',
                                               'org.openqms.d4.boundary.role': 'api'}}})
    monkeypatch.setattr(p, 'H', fake)
    receipt = dict(nonce='n', image_id='sha256:' + 'e' * 64,
                   objects=[{'id': 'b' * 64, 'role': 'api'}, {'id': 'a' * 64, 'role': 'api'}])
    assert not p.cleanup_objects(receipt)
    assert removed == ['a' * 64, 'b' * 64]
    assert receipt['cleanup_errors'] and 'must-not-leak' not in json.dumps(receipt)


def test_real_custom_profile_boundary_without_authority(remote):
    image = os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE')
    assert image, 'explicit pinned image required'
    spec = importlib.util.spec_from_file_location('_boundary_bundle', HERE / 'test_runtime_wiring.py')
    wiring = importlib.util.module_from_spec(spec); spec.loader.exec_module(wiring)
    bundle, digest = wiring._package_bundle()
    source = (HERE / 'runtime_boundary_probe.py').read_text()
    constants = dict(PACKAGE_B64=bundle, PACKAGE_SHA256=digest,
                     WIRING_PROBE_SOURCE=(HERE / 'runtime_wiring_probe.py').read_text(),
                     WIRE_FIXTURE_SOURCE=(REPOSITORY / 'backend/tests/e2e/d4_text_wire_fixture.py').read_text(),
                     PROBE_SHA256=hashlib.sha256(source.encode()).hexdigest())
    script = ''.join(key + ' = ' + repr(value) + '\n' for key, value in constants.items()) + source
    output = remote('sudo -n /usr/bin/python3 -I -S -B - ' + shlex.quote(image) +
                    " <<'D4_RUNTIME_BOUNDARY'\n" + script + '\nD4_RUNTIME_BOUNDARY\n', timeout=180, check=False)
    print(output)
    receipts = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert len(receipts) == 1, output
    receipt = receipts[0]
    assert receipt['boundary_verified'] and receipt['resources_cleaned'] and receipt['failure_code'] is None, receipt
    assert receipt['entrypoint_overlay_only'] is True and receipt['controller_delivery_evidence'] is False, receipt
    assert 'runtime_boundary_verified' in output.splitlines(), output


def test_local_boundary_templates_compile_and_missing_libc_symbol_is_not_denial():
    p = local_probe()
    config = dict(target='172.17.0.3', gateway='172.17.0.1', api_pid=123,
                  host_file='/run/owned/private/sentinel', api_file='/tmp/owned-sentinel')
    compile(p.attack_source(config), '<owned-attack>', 'exec')
    compile('CONFIG=' + repr(dict(role='api', target='172.17.0.3', api_file='/tmp/owned')) + '\n' + p.SERVER,
            '<owned-api>', 'exec')
    assert "getattr(libc,name)(*args)" in p.ATTACK and 'except OSError as e:' in p.ATTACK
    assert 'except (OSError,AttributeError)' not in p.ATTACK
    with pytest.raises(p.BoundaryFailure): p.attack_source(dict(config, arbitrary_command='denied'))


def test_local_boundary_observer_does_not_hide_other_recipe_changes():
    p = local_probe(); cid = 'c' * 64; image = 'sha256:' + 'e' * 64
    raw = dict(Id=cid, Image=image, Config=dict(Entrypoint=['FIXED'], User='0'), HostConfig=dict(Memory=0))
    class Engine:
        def inspect(self, identity, deadline): return raw
    normalized = p.OverlayObserver(Engine(), cid, image, ['FIXED']).inspect(cid, 100)
    assert normalized['Config']['User'] == '0' and normalized['HostConfig']['Memory'] == 0


def test_local_boundary_attach_output_is_bounded_and_single_row():
    p = local_probe()
    assert p.read_row(iter((b'{"phase":', b'"pre"}\n'))) == {'phase': 'pre'}
    with pytest.raises(p.BoundaryFailure): p.read_row(iter((b'x' * 513,)))
    with pytest.raises(p.BoundaryFailure): p.read_row(iter((b'{}\n{}\n',)))
    with pytest.raises(p.BoundaryFailure): p.read_row(iter([b'x' * 512] * 18))


def test_local_boundary_pending_create_never_claims_clean_even_with_no_known_id(monkeypatch):
    p = local_probe()
    receipt = dict(objects=[], create_pending={'receiver': True})
    assert not p.cleanup_objects(receipt)
    assert receipt['cleanup_errors'] == ['create_unresolved']


def test_local_boundary_missing_libc_function_raises_instead_of_reporting_denied():
    import ast
    from types import SimpleNamespace
    p = local_probe()
    definition = next(node for node in ast.parse(p.ATTACK).body if isinstance(node, ast.FunctionDef) and node.name == 'call')
    namespace = {'libc': SimpleNamespace(), 'ctypes': SimpleNamespace(set_errno=lambda n: None, get_errno=lambda: 1)}
    exec(compile(ast.Module(body=[definition], type_ignores=[]), '<exact-libc-probe>', 'exec'), namespace)
    with pytest.raises(AttributeError): namespace['call']('missing_syscall')
