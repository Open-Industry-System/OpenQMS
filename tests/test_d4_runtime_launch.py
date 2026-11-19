import hashlib
import json
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


PROGRAM = Path(__file__).parents[1] / 'deploy/d4-acceptance/runtime_launch.py'
native = runpy.run_path(str(PROGRAM))
RuntimeLaunch = native['RuntimeLaunch']
LaunchError = native['LaunchError']
functions = RuntimeLaunch.run.__globals__


@pytest.fixture
def runtime(tmp_path):
    return RuntimeLaunch(tmp_path, 'a' * 64, 'b' * 64, 'c' * 64)


def test_manifest_is_pinned_and_checks_all_import_bytes(tmp_path, monkeypatch):
    entry = tmp_path / native['ENTRY']
    entry.parent.mkdir(parents=True)
    entry.write_bytes(b'# approved entry')
    private_config = tmp_path / native['MANIFEST']
    raw = json.dumps({native['ENTRY']: hashlib.sha256(entry.read_bytes()).hexdigest()}).encode()
    private_config.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    monkeypatch.setitem(functions, 'trusted_directory', lambda *a, **kw: None)
    monkeypatch.setitem(functions, 'read_owned', lambda path, *a, **kw: path.read_bytes())
    native['verify_bundle'](tmp_path, pin)
    entry.write_bytes(b'# candidate code')
    with pytest.raises(LaunchError, match='file_mismatch'):
        native['verify_bundle'](tmp_path, pin)
    entry.write_bytes(b'# approved entry')
    (entry.parent / 'replacement.py').write_text('# unreviewed import')
    with pytest.raises(LaunchError, match='unlisted'):
        native['verify_bundle'](tmp_path, pin)
    with pytest.raises(LaunchError, match='manifest_mismatch'):
        native['verify_bundle'](tmp_path, 'f' * 64)
    (entry.parent / 'replacement.py').unlink()
    (tmp_path / 'subprocess.py').write_text('# sibling module would shadow stdlib')
    with pytest.raises(LaunchError, match='unreviewed_entry'):
        native['verify_bundle'](tmp_path, pin)


def test_scoped_receiver_cleanup_uses_full_identity(runtime, monkeypatch):
    nonce, api, receiver, image = runtime.nonce, runtime.api_container_id, 'd' * 64, 'sha256:' + 'e' * 64
    snapshot = dict(container_id=receiver, image_id=image, api_container_id=api,
                    nonce=nonce, daemon_invocation='runtime-daemon', boot_id='runtime-boot')
    monkeypatch.setattr(runtime, 'read_state', lambda: dict(
        create_converged=True, receiver_id=receiver, snapshot=snapshot,
    ))

    original = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda path, *a, **kw:
                        'runtime-boot' if path.name == 'boot_id' else original(path, *a, **kw))
    commands = []
    removed = False
    row = dict(Id=receiver, Image=image, Config={'Labels': {native['NONCE_LABEL']: nonce}},
               HostConfig={'NetworkMode': 'container:' + api}, State={'Running': True})

    def command(args, **options):
        nonlocal removed
        commands.append(args)
        if args[0] == native['SYSTEMCTL']:
            return b'runtime-daemon\n'
        verb = args[2]
        if verb == 'ls':
            return b'' if removed else (receiver + '\n').encode()
        if verb == 'inspect':
            return json.dumps([row]).encode()
        assert verb == 'rm' and args[3:] == [receiver]
        removed = True
        return b''

    monkeypatch.setitem(functions, 'run_command', command)
    with pytest.raises(LaunchError, match='ownership'):
        runtime.remove_receiver({'container_id': receiver}, image)
    assert not removed
    row['State']['Running'] = False
    runtime.remove_receiver({'container_id': receiver}, image)
    assert removed
    assert all('-f' not in command for command in commands)


def test_native_launch_invokes_fixed_roles_and_returns_only_business_evidence(runtime, monkeypatch):
    monkeypatch.setitem(functions, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setitem(functions, 'verify_bundle', lambda root, digest: None)
    monkeypatch.setattr(runtime, 'deployment', lambda: 'sha256:' + 'e' * 64)
    monkeypatch.setattr(runtime, 'journal', lambda: None)
    calls = []
    state = dict(first_stdin_ns=1, watchdog_bound_verified=True)

    def observe(reader, deadline):
        calls.append('observed')
        assert reader() == state and deadline > 0
        return {'task_id': 'trusted-business-evidence'}

    class Process:
        def wait(self, timeout):
            return 1

        def poll(self):
            return 1

    def start(argv, **kwargs):
        calls.append(argv)
        assert kwargs['env'] == {} and kwargs['cwd'] == '/'
        return Process()

    monkeypatch.setitem(functions, 'os', SimpleNamespace(
        **{name: getattr(functions['os'], name) for name in
           ('open', 'fdopen', 'O_RDWR', 'O_CREAT', 'O_NOFOLLOW')},
        geteuid=lambda: 0,
        fstat=lambda descriptor: SimpleNamespace(st_mode=0o100600, st_uid=0, st_nlink=1),
    ))
    monkeypatch.setitem(functions, 'subprocess', SimpleNamespace(
        Popen=start, DEVNULL=-3, TimeoutExpired=functions['subprocess'].TimeoutExpired,
    ))
    states = iter((None, state, state))
    monkeypatch.setattr(runtime, 'read_state', lambda: next(states))
    monkeypatch.setattr(runtime, 'wait_reclaimed', lambda deadline: {'state': 'closed'})
    monkeypatch.setattr(runtime, 'remove_receiver', lambda *_: calls.append('reclaimed'))
    assert runtime.run(observe) == {'task_id': 'trusted-business-evidence'}
    assert calls[0][-3:] == ['launch', '--nonce', runtime.nonce]
    assert calls[1:] == ['observed', 'reclaimed']


def test_replayed_nonce_is_rejected_before_launch(runtime, monkeypatch):
    monkeypatch.setitem(functions, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setitem(functions, 'os', SimpleNamespace(
        **{name: getattr(functions['os'], name) for name in
           ('open', 'fdopen', 'O_RDWR', 'O_CREAT', 'O_NOFOLLOW')},
        geteuid=lambda: 0,
        fstat=lambda descriptor: SimpleNamespace(st_mode=0o100600, st_uid=0, st_nlink=1),
    ))
    monkeypatch.setitem(functions, 'verify_bundle', lambda root, digest: None)
    monkeypatch.setattr(runtime, 'deployment', lambda: 'sha256:' + 'e' * 64)
    monkeypatch.setattr(runtime, 'journal', lambda: {'state': 'closed'})
    monkeypatch.setitem(functions, 'subprocess', SimpleNamespace(Popen=lambda *a, **kw: pytest.fail('unexpected launch')))
    with pytest.raises(LaunchError, match='nonce_has_been_used'):
        runtime.run(lambda *_: pytest.fail('unexpected observer'))
