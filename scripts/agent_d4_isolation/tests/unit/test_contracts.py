import dataclasses
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location('_i1_helpers_contracts', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
c = h.load('contracts')


@pytest.fixture(autouse=True)
def pure(monkeypatch):
    h.guard(monkeypatch)


@pytest.fixture
def value():
    return dict(origin='http://127.0.0.1:8000', tenant_slug='test-tenant',
                installation_id='12345678-1234-4234-8234-123456789012',
                secret='synthetic-secret-123456789', request_key='request-1',
                expected_report_id='22345678-1234-4234-8234-123456789012')


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def private(tmp_path, raw):
    directory = Path(os.path.realpath(tmp_path)) / 'private'
    directory.mkdir(mode=0o700)
    path = directory / 'config.json'
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def test_guard_is_in_process_not_os_denial():
    """Probe harmless targets; `asyncpg` is installed in the test venv, so the
    import assertion is meaningful rather than trivially satisfied."""
    with pytest.raises(AssertionError):
        socket.socket()
    with pytest.raises(AssertionError):
        subprocess.run(['/bin/echo', 'probe'])
    with pytest.raises(ModuleNotFoundError):
        __import__('asyncpg')


def test_valid_frozen_stdin(value):
    config = c.parse_config(encode(value))
    assert json.loads(config.to_stdin()) == value


def test_config_repr_hides_secret_origin_and_request_key(value):
    config = c.parse_config(encode(value))
    assert value['secret'] not in repr(config)
    assert value['request_key'] not in repr(config)
    assert value['origin'] not in repr(config)


def test_config_is_frozen(value):
    config = c.parse_config(encode(value))
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.secret = 'changed'


def test_child_environment_declaration_is_empty():
    """Declarative only: nothing is spawned in I1."""
    assert c.clean_environment() == {}


def test_lone_surrogate_secret_is_rejected(value):
    value['secret'] = '\ud800' * 20
    with pytest.raises(c.ContractError):
        c.parse_config(json.dumps(value, ensure_ascii=True).encode('utf-8'))


@pytest.mark.parametrize('key,item', [
    ('origin', 'http://localhost:8000'), ('origin', 'http://127.1:8000'),
    ('origin', 'http://127.0.0.1/'), ('origin', 'http://127.0.0.1?'),
    ('origin', 'http://127.0.0.1#'), ('origin', 'http://user@127.0.0.1'),
    ('origin', 'http://127.0.0.1:080'), ('origin', 'http://127.0.0.1:0'),
    ('origin', 'http://127.0.0.1:65536'), ('origin', 'ftp://127.0.0.1'),
    ('origin', 'http://127.0.0.1\\evil'), ('origin', ' http://127.0.0.1'),
    ('origin', 'http://[::ffff:127.0.0.1]'), ('tenant_slug', 'UPPER'),
    ('tenant_slug', ''), ('installation_id', '123'), ('expected_report_id', 'bad'),
    ('secret', 'short'), ('secret', 'x' * 201), ('request_key', ''),
    ('request_key', 'x' * 101), ('secret', 123), ('origin', None),
    ('origin', 'http://127.0.0.1:999999999999'),
])
def test_invalid_field(value, key, item):
    value[key] = item
    with pytest.raises(c.ContractError, match='^configuration_invalid$'):
        c.parse_config(encode(value))


@pytest.mark.parametrize('origin', ['http://127.0.0.1', 'https://127.0.0.1:443', 'http://[::1]:8000', 'https://[::1]'])
def test_existing_numeric_origin_formats(value, origin):
    value['origin'] = origin
    assert c.parse_config(encode(value)).origin == origin


@pytest.mark.parametrize('raw', [b'[]', b'null', b'{}', b'{', b'\xff', b'{"secret":"SENTINEL","secret":"other"}'])
def test_bad_json_no_dynamic_diagnostic(raw):
    with pytest.raises(c.ContractError) as error:
        c.parse_config(raw)
    assert str(error.value) == 'configuration_invalid'
    assert error.value.__context__ is None


def test_exact_six_keys_rejected_when_extended_or_shortened(value):
    for changed in (dict(value, env={'SECRET': value['secret']}), {k: v for k, v in value.items() if k != 'secret'}):
        with pytest.raises(c.ContractError):
            c.parse_config(encode(changed))


def test_encoded_stdin_budget_is_enforced(value):
    # Unicode lengths remain the existing contract, encoded input is separately bounded.
    value['secret'] = '界' * 200
    assert c.parse_config(encode(value)).secret == value['secret']
    raw = encode(value)
    assert c.parse_config(raw + b' ' * (c.CONFIG_LIMIT - len(raw))) is not None
    with pytest.raises(c.ContractError):
        c.parse_config(raw + b' ' * (c.CONFIG_LIMIT + 1 - len(raw)))
    with pytest.raises(c.ContractError):
        c.PrivateConfig(**dict(value, origin='http://evil'))


def test_real_private_file(tmp_path, value):
    path = private(tmp_path, encode(value))
    assert json.loads(c.read_private_config(path).to_stdin()) == value


@pytest.mark.parametrize('change', ['directory-mode', 'file-mode', 'hardlink', 'file-symlink', 'ancestor-symlink', 'fifo', 'oversize', 'dotdot'])
def test_unsafe_file(tmp_path, value, change):
    path = private(tmp_path, encode(value))
    if change == 'directory-mode':
        path.parent.chmod(0o750)
    elif change == 'file-mode':
        path.chmod(0o640)
    elif change == 'hardlink':
        os.link(path, path.with_name('alias'))
    elif change == 'file-symlink':
        target = path.with_name('target')
        path.rename(target)
        path.symlink_to(target)
    elif change == 'ancestor-symlink':
        link = path.parent.parent / 'link'
        link.symlink_to(path.parent, target_is_directory=True)
        path = link / path.name
    elif change == 'fifo':
        path.unlink()
        os.mkfifo(path, 0o600)
    elif change == 'oversize':
        path.write_bytes(b' ' * (c.CONFIG_LIMIT + 1))
    elif change == 'dotdot':
        path = path.parent / '..' / 'private' / path.name
    with pytest.raises(c.ContractError) as error:
        c.read_private_config(path)
    # Fixed message with no chained OS error: a filename or JSON fragment here
    # would reach the I6 log chain.
    assert str(error.value) == 'configuration_invalid'
    assert error.value.__context__ is None


@pytest.mark.parametrize('which', ['file', 'directory'])
def test_wrong_owner(tmp_path, value, monkeypatch, which):
    path = private(tmp_path, encode(value))
    original = os.fstat
    def wrong(fd):
        info = original(fd)
        if (which == 'file' and stat.S_ISREG(info.st_mode)) or (which == 'directory' and stat.S_ISDIR(info.st_mode) and info.st_ino == path.parent.stat().st_ino):
            fields = list(info)
            fields[4] = info.st_uid + 1  # os.stat_result index 4 is st_uid
            return os.stat_result(fields)
        return info
    monkeypatch.setattr(os, 'fstat', wrong)
    with pytest.raises(c.ContractError) as error:
        c.read_private_config(path)
    assert str(error.value) == 'configuration_invalid'
    assert error.value.__context__ is None


def test_failed_reads_do_not_leak_descriptors(tmp_path, value, monkeypatch):
    path = private(tmp_path, encode(value))
    path.chmod(0o640)  # rejected after both the directory and file were opened
    real_open, real_close = os.open, os.close
    counts = {'open': 0, 'close': 0}
    def counting_open(*args, **kwargs):
        counts['open'] += 1
        return real_open(*args, **kwargs)
    def counting_close(fd):
        counts['close'] += 1
        return real_close(fd)
    monkeypatch.setattr(os, 'open', counting_open)
    monkeypatch.setattr(os, 'close', counting_close)
    for _ in range(5):
        with pytest.raises(c.ContractError):
            c.read_private_config(path)
    assert counts['open'] > 0
    assert counts['open'] == counts['close']


def test_pinned_directory_resists_replacement(tmp_path, value, monkeypatch):
    path = private(tmp_path, encode(value))
    replacement = path.parent.parent / 'replacement'
    replacement.mkdir(mode=0o700)
    (replacement / path.name).write_bytes(encode(dict(value, secret='attacker-secret-123456789')))
    (replacement / path.name).chmod(0o600)
    original = os.open
    swapped = False
    def opening(name, flags, *args, **kwargs):
        nonlocal swapped
        if name == path.name and not swapped:
            swapped = True
            path.parent.rename(path.parent.with_name('pinned'))
            path.parent.symlink_to(replacement, target_is_directory=True)
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', opening)
    assert c.read_private_config(path).secret == value['secret']
    assert swapped


def test_swap_component_to_symlink_is_refused(tmp_path, value, monkeypatch):
    path = private(tmp_path, encode(value))
    original = os.open
    swapped = False
    def opening(name, flags, *args, **kwargs):
        nonlocal swapped
        if name == 'private' and not swapped:
            swapped = True
            destination = path.parent.with_name('moved')
            path.parent.rename(destination)
            path.parent.symlink_to(destination, target_is_directory=True)
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', opening)
    with pytest.raises(c.ContractError) as error:
        c.read_private_config(path)
    assert str(error.value) == 'configuration_invalid'
    assert error.value.__context__ is None
    assert swapped


def test_duplicate_key_with_full_six_fields_is_rejected(value):
    """All six keys present; only `secret` repeats.

    The other duplicate-key case in this file omits keys, so it would be
    rejected by the key-set check alone. This one can only fail through
    object_pairs_hook: without it json.loads keeps the last value.
    """
    raw = encode(value)
    duplicated = raw.replace(
        b'"secret":"' + value['secret'].encode() + b'"',
        b'"secret":"' + value['secret'].encode() + b'","secret":"attacker-secret-1234567"', 1)
    assert duplicated != raw and duplicated.count(b'"secret"') == 2
    with pytest.raises(c.ContractError) as error:
        c.parse_config(duplicated)
    assert str(error.value) == 'configuration_invalid'


def test_size_change_between_checks_is_refused(tmp_path, value, monkeypatch):
    """The post-read fstat comparison is the only guard against a same-owner
    writer changing the file after the first fstat."""
    path = private(tmp_path, encode(value))
    original = os.fstat
    seen = {'regular': 0}
    def changing(fd):
        info = original(fd)
        if stat.S_ISREG(info.st_mode):
            seen['regular'] += 1
            if seen['regular'] >= 2:
                fields = list(info)
                fields[6] = info.st_size + 1  # index 6 is st_size
                return os.stat_result(fields)
        return info
    monkeypatch.setattr(os, 'fstat', changing)
    with pytest.raises(c.ContractError):
        c.read_private_config(path)
    assert seen['regular'] >= 2


def test_growth_past_budget_after_first_fstat_is_refused(tmp_path, value, monkeypatch):
    """An understated first fstat still cannot deliver oversized bytes.

    The read path rejects them; that rejection is defence in depth, since the
    open-time `st_size` bound and parse_config's own length bound overlap, so no
    single line can be falsified alone.
    """
    path = private(tmp_path, encode(value))
    path.write_bytes(encode(value) + b' ' * c.CONFIG_LIMIT)
    original = os.fstat
    def understating(fd):
        info = original(fd)
        if stat.S_ISREG(info.st_mode):
            fields = list(info)
            fields[6] = 10  # claim a small file
            return os.stat_result(fields)
        return info
    monkeypatch.setattr(os, 'fstat', understating)
    with pytest.raises(c.ContractError):
        c.read_private_config(path)


def permit_value():
    return dict(image_digest='sha256:' + 'a' * 64, worker_sha256=c.WORKER_SHA256,
                receiver_uid=2001, api_uid=2002, api_port=8000)


@pytest.mark.parametrize('key,item', [('image_digest', 'receiver:latest'), ('image_digest', 'registry/image@sha256:' + 'a'*64),
    ('worker_sha256', 'b'*64), ('receiver_uid', 0), ('receiver_uid', True), ('api_uid', 2001),
    ('receiver_uid', 2**32), ('api_uid', 2**63), ('receiver_uid', -(2001)),
    ('api_port', False), ('api_port', 1.0), ('api_port', 0), ('api_port', 65536),
    ('command', ['sh']), ('mount', '/'), ('runtime', 'custom'), ('capabilities', ['SYS_ADMIN']),
    ('network', 'host'), ('pid', 'host'), ('env', {'SECRET': 'x'}), ('argv', ['secret'])])
def test_permit_closed_schema(key, item):
    value = permit_value()
    value[key] = item
    with pytest.raises(c.ContractError):
        c.DeploymentPermit.from_mapping(value)


def test_permit_binding_requires_matching_ipv4_loopback_port(value):
    permit = c.DeploymentPermit.from_mapping(permit_value())
    c.validate_binding(c.parse_config(encode(value)), permit)
    value['origin'] = 'http://[::1]:8000'
    with pytest.raises(c.ContractError):
        c.validate_binding(c.parse_config(encode(value)), permit)
    value['origin'] = 'http://127.0.0.1:8001'
    with pytest.raises(c.ContractError):
        c.validate_binding(c.parse_config(encode(value)), permit)


def test_infrastructure_result_allows_only_fixed_statuses():
    for status in ('isolation_exited', 'isolation_terminated', 'isolation_unknown'):
        assert c.InfrastructureResult(status).as_dict() == {'status': status}
    # Receiver self-reports are not representable, so they cannot be forwarded.
    for status in ('completed', 'unknown', {'completed': True}, 0):
        with pytest.raises(c.ContractError):
            c.InfrastructureResult(status)
    with pytest.raises(TypeError):
        c.InfrastructureResult('isolation_exited', receipt_id='encoded-secret')


SPAWN_PREFIXES = ('exec', 'spawn', 'fork', 'system', 'popen', 'posix_spawn')


def os_spawn_names():
    """Derive the probe set from this platform's os module, not from the guard list.

    A hand-copied list can only prove the two copies agree; it cannot notice a
    primitive the guard itself forgot.
    """
    return tuple(sorted(name for name in dir(os)
                        if name.startswith(SPAWN_PREFIXES) and callable(getattr(os, name))))


def test_guard_replaces_every_platform_os_spawn_name():
    """Identity probe only: calling exec/fork here would run or replace pytest.

    "Every" is scoped to names in the os namespace matching SPAWN_PREFIXES;
    pty.fork, multiprocessing and C-level _socket are outside this list.
    """
    names = os_spawn_names()
    assert {'fork', 'forkpty', 'execv', 'execve', 'system', 'popen', 'posix_spawn'} <= set(names)
    original = {name: getattr(os, name) for name in names}
    with pytest.MonkeyPatch.context() as monkeypatch:
        h.guard(monkeypatch)
        missed = [name for name, value in original.items() if getattr(os, name) is value]
    assert missed == [], missed


def test_guard_lists_cover_platform_spawn_names():
    """Bidirectional: the guard list must neither miss nor invent platform names.

    The duplicated prefix list in this file is deliberate independence — the
    probe must not read the guard's own list — so compare the two derived sets.
    """
    assert set(os_spawn_names()) == set(h.SPAWN_NAMES)


def test_receiver_entrypoint_constant_is_fixed():
    assert c.RECEIVER_ENTRYPOINT == ('python', '-I', '-S', '-B', '/receiver.py')


def test_package_entry_runs_under_guard(tmp_path):
    root = tmp_path / 'pkg'
    root.mkdir()
    (root / '__init__.py').write_text('import socket\nsocket.socket()\n')
    with pytest.raises(AssertionError):
        h.load_package(root, '_i1_guard_pkg')
    assert '_i1_guard_pkg' not in sys.modules


def test_failed_module_import_is_not_cached(tmp_path):
    root = tmp_path / 'pkg2'
    root.mkdir()
    (root / '__init__.py').write_text('')
    (root / 'side.py').write_text('import os\nos.fork()\n')
    for attempt in range(2):
        with pytest.raises(AssertionError):
            h.load('side', root=root, package='_i1_guard_pkg2')
        assert '_i1_guard_pkg2.side' not in sys.modules, attempt


def test_module_cannot_import_database_client(tmp_path):
    root = tmp_path / 'pkg3'
    root.mkdir()
    (root / '__init__.py').write_text('')
    (root / 'db.py').write_text('import asyncpg\n')
    with pytest.raises(ImportError):
        h.load('db', root=root, package='_i1_guard_pkg3')
    assert '_i1_guard_pkg3.db' not in sys.modules
