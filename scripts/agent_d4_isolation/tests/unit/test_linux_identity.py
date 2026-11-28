"""Collector behaviour with fake Engine/kernel observations; no Linux claims."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('_identity_helpers', Path(__file__).resolve().parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

NONCE, CID, API = 'a' * 64, 'c' * 64, 'd' * 64
IMAGE = 'sha256:' + 'e' * 64
DEADLINE = 10 ** 30


def test_collector_module_exists():
    assert (h.ROOT / 'linux_identity.py').is_file(), 'real Linux collector missing'


@pytest.fixture
def m():
    return h.load('linux_identity')


class Process:
    def __init__(self, pid, uid):
        self.pid, self.starttime, self.uid = pid, pid * 10, uid
        self.live, self.closed = True, False

    def alive(self):
        return self.live and not self.closed

    def read(self, name):
        if name == 'uid_map':
            return '0 0 4294967295\n'
        if name == 'status':
            return f'Uid:\t{self.uid}\t{self.uid}\t{self.uid}\t{self.uid}\nCapEff:\t0000000000000000\nCapPrm:\t0\nCapBnd:\t0\nCapInh:\t0\nCapAmb:\t0\nNoNewPrivs:\t1\nSeccomp:\t2\n'
        raise AssertionError(name)

    def close(self):
        self.closed = True


class Ref:
    def __init__(self, inode, path=None):
        self.device, self.inode, self.path = 4, inode, path
        self.closed, self.count, self.kills = False, 1, 0

    def alive(self):
        return not self.closed

    def tasks_remaining(self):
        return self.count

    def kill(self):
        self.kills += 1
        self.count = 0

    def close(self):
        self.closed = True


class Host:
    def __init__(self):
        self.generation = 'f' * 32
        self.refs = []
        self.receiver_start = 110
        self.ns_inode = 99

    def daemon(self, deadline_ns):
        p = Process(1, 0)
        self.refs.append(p)
        return p, self.generation, 'feedface-cafe-beef-feed-facecafebeef'

    def pin(self, pid):
        p = Process(pid, {11: 2001, 22: 2002}[pid])
        if pid == 11:
            p.starttime = self.receiver_start
        self.refs.append(p)
        return p

    def netns(self, process):
        r = Ref(self.ns_inode)
        self.refs.append(r)
        return r

    def cgroup(self, process):
        r = Ref(88, '/system.slice/docker-' + CID + '.scope')
        self.refs.append(r)
        return r

    def verify_limits(self, process, cgroup):
        pass


def expected_recipe(nonce, image, api):
    return {'Image': image, 'User': '2001:2001', 'Entrypoint': ['python', '-I', '-S', '-B', '/receiver.py'],
            'Cmd': [], 'Labels': {'org.openqms.d4.nonce': nonce}, 'OpenStdin': True,
            'HostConfig': {'NetworkMode': 'container:' + api, 'ReadonlyRootfs': True,
                           'Privileged': False, 'CapDrop': ['ALL'], 'CapAdd': [],
                           'Memory': 134217728, 'MemorySwap': 134217728,
                           'PidsLimit': 16, 'NanoCpus': 1000000000,
                           'Binds': [], 'Tmpfs': {'/tmp': 'rw,nodev,nosuid,noexec,size=8m,nr_inodes=128'},
                           'SecurityOpt': ['no-new-privileges', 'seccomp={"defaultAction":"SCMP_ACT_ERRNO"}'],
                           'Ulimits': [{'Name': 'nofile', 'Soft': 64, 'Hard': 64}, {'Name': 'core', 'Soft': 0, 'Hard': 0}],
                           'LogConfig': {'Type': 'none', 'Config': {}}}}


class Engine:
    def __init__(self):
        recipe = expected_recipe(NONCE, IMAGE, API)
        self.receiver = {'Id': CID, 'Image': IMAGE, 'Config': {k: v for k, v in recipe.items() if k != 'HostConfig'},
                         'HostConfig': recipe['HostConfig'], 'State': {'Pid': 11, 'Running': True}, 'Mounts': []}
        self.receiver['Config']['Env'] = ['SECRET=must-not-escape']
        self.api = {'Id': API, 'Config': {'User': '2002:2002'}, 'State': {'Pid': 22, 'Running': True}}
        self.signals = []
        self.failed = False

    def inspect(self, cid, deadline_ns):
        if self.failed:
            raise OSError('secret engine error')
        return copy.deepcopy(self.receiver if cid == CID else self.api)

    def inspect_image(self, image, deadline_ns):
        return {'Id': IMAGE, 'Config': {'User': '2001:2001', 'Entrypoint': ['python', '-I', '-S', '-B', '/receiver.py'], 'Env': ['SECRET=must-not-escape']}}

    def info(self, deadline_ns):
        return {'CgroupVersion': '2', 'SecurityOptions': ['name=seccomp,profile=builtin']}

    def signal(self, cid, signal, deadline_ns):
        self.signals.append((cid, signal))


@pytest.fixture
def setup(m, monkeypatch):
    host, engine = Host(), Engine()
    monkeypatch.setattr(m, '_Host', lambda: host)
    monkeypatch.setattr(m, '_recipe', expected_recipe)
    collector = m.KernelCollector(engine, IMAGE, API)
    return collector, engine, host


def test_bind_keeps_live_refs_and_exports_only_safe_facts(m, setup):
    collector, engine, host = setup
    binding = collector.bind(NONCE, CID, DEADLINE)
    snapshot = binding.snapshot()
    assert snapshot['container_id'] == CID and snapshot['receiver_host_uid'] == 2001
    assert 'must-not-escape' not in json.dumps(snapshot)
    assert set(snapshot) == m.SNAPSHOT_KEYS
    assert collector.revalidate(binding, DEADLINE).container_id == CID
    binding.close()
    assert all(x.closed for x in host.refs)
    assert collector.revalidate(binding, DEADLINE) is None


@pytest.mark.parametrize('section,key,value', [
    ('Config', 'User', '0'), ('Config', 'Entrypoint', ['sh']),
    ('HostConfig', 'ReadonlyRootfs', False), ('HostConfig', 'Memory', 0),
    ('HostConfig', 'MemorySwap', -1), ('HostConfig', 'PidsLimit', 0),
    ('HostConfig', 'NanoCpus', 0), ('HostConfig', 'CapAdd', ['SYS_ADMIN']),
    ('HostConfig', 'Privileged', True), ('HostConfig', 'Binds', ['/var/run/docker.sock:/sock']),
    ('HostConfig', 'SecurityOpt', []), ('HostConfig', 'Tmpfs', {'/tmp': 'rw'}),
    ('HostConfig', 'Ulimits', []), ('HostConfig', 'LogConfig', {'Type': 'json-file'}),
    ('HostConfig', 'NetworkMode', 'host')])
def test_unsafe_recipe_never_binds(m, setup, section, key, value):
    collector, engine, host = setup
    engine.receiver[section][key] = value
    with pytest.raises(m.IdentityError, match='^identity_unverified$'):
        collector.bind(NONCE, CID, DEADLINE)
    assert all(x.closed for x in host.refs)


@pytest.mark.parametrize('change', ['daemon', 'pid_reuse', 'namespace', 'engine_unavailable'])
def test_changed_identity_is_never_revalidated(m, setup, change):
    collector, engine, host = setup
    binding = collector.bind(NONCE, CID, DEADLINE)
    if change == 'daemon': host.generation = 'b' * 32
    elif change == 'pid_reuse': host.receiver_start += 1
    elif change == 'namespace': host.ns_inode += 1
    else: engine.failed = True
    assert collector.revalidate(binding, DEADLINE) is None
    assert binding.signal('SIGKILL', DEADLINE) is False
    assert engine.signals == []
    binding.close()


def test_live_binding_kills_only_retained_cgroup_and_closed_binding_cannot_kill(m, setup):
    collector, engine, host = setup
    binding = collector.bind(NONCE, CID, DEADLINE)
    assert binding.tasks_remaining() == 1
    assert binding.terminate(DEADLINE).terminated
    assert binding.tasks_remaining() == 0 and binding.cgroup.kills == 1
    binding.close()
    assert binding.tasks_remaining() is None
    assert not binding.terminate(DEADLINE).terminated
    assert binding.cgroup.kills == 1


def test_cgroup_kill_failure_is_unknown(m, setup):
    collector, engine, host = setup
    binding = collector.bind(NONCE, CID, DEADLINE)
    binding.cgroup.kill = lambda: (_ for _ in ()).throw(OSError('sensitive path'))
    result = binding.terminate(DEADLINE)
    assert not result.terminated and result.reason == 'unknown'
    binding.close()


def test_container_running_requires_current_daemon_and_exact_container(m, setup):
    collector, engine, host = setup
    binding = collector.bind(NONCE, CID, DEADLINE)
    assert binding.container_running(DEADLINE) is True
    engine.receiver['State']['Running'] = False
    assert binding.container_running(DEADLINE) is False
    host.generation = 'b' * 32
    assert binding.container_running(DEADLINE) is None
    binding.close()


def test_fresh_stop_binding_rechecks_snapshot_and_cannot_recreate_kernel_authority(m, setup):
    collector, engine, host = setup
    original = collector.bind(NONCE, CID, DEADLINE)
    snapshot = original.snapshot()
    original.close()
    fresh = m.fresh_stop_binding(snapshot, NONCE, DEADLINE, engine=engine)
    assert fresh is not None
    assert fresh.signal('SIGTERM', DEADLINE)
    assert engine.signals == [(CID, 'SIGTERM')]
    assert not fresh.terminate(DEADLINE).terminated
    fresh.close()
    host.receiver_start += 1
    assert m.fresh_stop_binding(snapshot, NONCE, DEADLINE, engine=engine) is None
    assert m.fresh_stop_binding(snapshot, 'b' * 64, DEADLINE, engine=engine) is None
    engine.failed = True
    assert m.fresh_stop_binding(snapshot, NONCE, DEADLINE, engine=engine) is None


def test_proc_stat_parser_handles_spaces_and_parentheses(m):
    fields = ['S'] + ['0'] * 18 + ['1234'] + ['0'] * 3
    assert m._starttime('11 (a name (worker)) ' + ' '.join(fields)) == 1234
    with pytest.raises(m.IdentityError):
        m._starttime('bad')


def test_cgroup_events_covers_descendants_and_never_claims_unreadable_as_empty(m, tmp_path):
    import os
    root = tmp_path / 'cg'
    root.mkdir()
    (root / 'cgroup.events').write_text('populated 1\nfrozen 0\n')
    (root / 'cgroup.procs').write_text('11\n')
    child = root / 'child'; child.mkdir()
    (child / 'cgroup.procs').write_text('33\n')
    (root / 'cgroup.kill').write_text('')
    ref = m._Cgroup(os.open(root, os.O_RDONLY | os.O_DIRECTORY), '/only-a-locator')
    assert ref.tasks_remaining() == 2
    ref.kill()
    assert (root / 'cgroup.kill').read_text() == '1'
    (root / 'cgroup.events').write_text('populated 0\nfrozen 0\n')
    assert ref.tasks_remaining() == 0
    # A retained events fd is evidence even if the original directory is removed.
    (root / 'cgroup.events').unlink()
    (root / 'cgroup.procs').unlink()
    (root / 'cgroup.kill').unlink()
    (child / 'cgroup.procs').unlink(); child.rmdir(); root.rmdir()
    assert ref.tasks_remaining() == 0
    ref.close()
    assert ref.tasks_remaining() is None


@pytest.mark.parametrize('text', ['populated 1\n', 'unreadable\n'])
def test_populated_cgroup_with_zero_visible_pids_is_unknown(m, tmp_path, text):
    import os
    (tmp_path / 'cgroup.events').write_text(text)
    (tmp_path / 'cgroup.procs').write_text('')
    ref = m._Cgroup(os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY), '/locator')
    assert ref.tasks_remaining() is None
    ref.close()


def test_kernel_limits_readback_rejects_relaxed_cpu_and_swap(m):
    class Proc:
        def read(self, key):
            if key == 'limits':
                return 'Max open files            64                   64                   files\nMax core file size        0                    0                    bytes\n'
            if key == 'mountinfo':
                return '1 2 0:1 / / ro - overlay overlay ro\n3 2 0:2 / /tmp rw,nosuid,nodev,noexec - tmpfs tmpfs rw,size=8192k,nr_inodes=128\n'
            raise AssertionError(key)
    class CG:
        def read(self, key):
            return self.values[key]
        values = {'memory.max': '134217728', 'memory.swap.max': '0', 'pids.max': '16', 'cpu.max': '100000 100000'}
    cg = CG()
    m._Host().verify_limits(Proc(), cg)
    cg.values = dict(cg.values, **{'cpu.max': '200000 100000'})
    with pytest.raises(m.IdentityError): m._Host().verify_limits(Proc(), cg)
    cg.values = dict(cg.values, **{'cpu.max': '100000 100000', 'memory.swap.max': '134217728'})
    with pytest.raises(m.IdentityError): m._Host().verify_limits(Proc(), cg)


def test_real_recipe_and_frozen_image_environment_are_enforced(m, setup, monkeypatch):
    collector, engine, host = setup
    real_recipe = h.load('linux_engine').recipe
    body = real_recipe(NONCE, IMAGE, API)
    engine.receiver['Config'] = {k: v for k, v in body.items() if k != 'HostConfig'}
    engine.receiver['Config']['Env'] = ['PATH=/fixed/image/bin']
    engine.receiver['HostConfig'] = body['HostConfig']
    engine.inspect_image = lambda image, deadline_ns: {'Id': IMAGE, 'Config': {
        'User': '2001:2001', 'Entrypoint': body['Entrypoint'], 'Env': ['PATH=/fixed/image/bin']}}
    monkeypatch.setattr(m, '_recipe', real_recipe)
    binding = collector.bind(NONCE, CID, DEADLINE)
    binding.close()
    engine.receiver['Config']['Env'].append('OPENAI_API_KEY=not-allowed')
    with pytest.raises(m.IdentityError): collector.bind(NONCE, CID, DEADLINE)


@pytest.mark.parametrize('key,value', [
    ('Devices', [{'PathOnHost': '/dev/sda'}]), ('DeviceRequests', [{'Count': -1}]),
    ('DeviceCgroupRules', ['a *:* rwm']), ('GroupAdd', ['0']),
    ('VolumesFrom', ['host-source']), ('Sysctls', {'net.ipv4.ip_forward': '1'}),
    ('Mounts', [{'Type': 'bind', 'Source': '/'}]), ('Runtime', 'untrusted-runtime'),
    ('OomKillDisable', True)])
def test_extra_privileged_host_configuration_is_rejected(m, setup, key, value):
    collector, engine, host = setup
    engine.receiver['HostConfig'][key] = value
    with pytest.raises(m.IdentityError): collector.bind(NONCE, CID, DEADLINE)


@pytest.mark.parametrize('change', ['valid', 'running', 'wrong_status', 'wrong_image', 'wrong_nonce', 'pid_bool'])
def test_created_only_verification_never_authorises_running_or_unrelated_container(m, setup, change):
    collector, engine, host = setup
    engine.receiver['State'] = {'Pid': 0, 'Running': False, 'Status': 'created', 'Restarting': False}
    if change == 'running': engine.receiver['State']['Running'] = True
    elif change == 'wrong_status': engine.receiver['State']['Status'] = 'exited'
    elif change == 'wrong_image': engine.receiver['Image'] = 'sha256:' + 'f' * 64
    elif change == 'wrong_nonce': engine.receiver['Config']['Labels'] = {'org.openqms.d4.nonce': 'b' * 64}
    elif change == 'pid_bool': engine.receiver['State']['Pid'] = False
    assert collector.verify_created(NONCE, CID, DEADLINE) is (change == 'valid')
    assert engine.signals == []


def test_snapshot_schema_rejects_extra_keys_and_boolean_version(m, setup):
    collector, engine, host = setup
    binding = collector.bind(NONCE, CID, DEADLINE)
    snapshot = binding.snapshot(); binding.close()
    assert m.fresh_stop_binding(dict(snapshot, version=True), NONCE, DEADLINE, engine=engine) is None
    assert m.fresh_stop_binding(dict(snapshot, extra='untrusted'), NONCE, DEADLINE, engine=engine) is None


def test_fresh_reclaim_does_not_depend_on_api_still_running_and_never_delivers(m, setup):
    collector, engine, host = setup
    original = collector.bind(NONCE, CID, DEADLINE)
    snapshot = original.snapshot(); original.close()
    engine.api['State']['Running'] = False
    fresh = m.fresh_stop_binding(snapshot, NONCE, DEADLINE, engine=engine)
    assert fresh is not None
    assert fresh.collector.revalidate(fresh, DEADLINE, delivery=True) is None
    assert fresh.signal('SIGKILL', DEADLINE)
    assert engine.signals == [(CID, 'SIGKILL')]
    fresh.close()


@pytest.mark.parametrize('field', ['CapEff', 'CapPrm', 'CapBnd', 'CapInh', 'CapAmb'])
def test_actual_kernel_capabilities_must_all_be_empty(m, setup, field):
    collector, engine, host = setup
    old_pin = host.pin
    def pin(pid):
        process = old_pin(pid)
        read = process.read
        def changed(name):
            result = read(name)
            if name == 'status' and pid == 11:
                lines = [x for x in result.splitlines() if not x.startswith(field + ':')]
                return '\n'.join(lines + [field + ':\t0000000000000001']) + '\n'
            return result
        process.read = changed
        return process
    host.pin = pin
    with pytest.raises(m.IdentityError): collector.bind(NONCE, CID, DEADLINE)


def test_pidfd_exit_or_reused_starttime_invalidates_proc_reference(m, monkeypatch):
    state = {'start': 123, 'exited': False}
    closed = []
    monkeypatch.setattr(m.os, 'open', lambda *a, **kw: 10)
    monkeypatch.setattr(m.os, 'pidfd_open', lambda *a: 11, raising=False)
    monkeypatch.setattr(m.os, 'close', closed.append)
    monkeypatch.setattr(m, '_read_at', lambda fd, name: '11 (receiver) ' + ' '.join(['S'] + ['0'] * 18 + [str(state['start'])]))
    class Poll:
        def register(self, *a): pass
        def poll(self, timeout): return [(11, 1)] if state['exited'] else []
    monkeypatch.setattr(m.select, 'poll', Poll)
    process = m._Process(11)
    assert process.alive()
    state['start'] += 1
    assert not process.alive()
    state['start'] -= 1; state['exited'] = True
    assert not process.alive()
    process.close(); process.close()
    assert sorted(closed) == [10, 11]


def test_preparation_daemon_lease_pins_generation_before_create(m, setup):
    collector, engine, host = setup
    lease = collector.pin_daemon(DEADLINE)
    assert lease.snapshot() == {'boot_id': 'feedface-cafe-beef-feed-facecafebeef',
        'daemon_invocation': 'f' * 32, 'daemon_pid': 1, 'daemon_starttime': 10}
    assert lease.current(DEADLINE)
    host.generation = 'b' * 32
    assert not lease.current(DEADLINE)
    host.generation = 'f' * 32
    assert not lease.current(DEADLINE), 'invalidation must be permanent'
    lease.close(); lease.close()
    assert not lease.current(DEADLINE)
    assert all(ref.closed for ref in host.refs)


def test_preparation_daemon_lease_checks_retained_pidfd(m, setup):
    collector, engine, host = setup
    lease = collector.pin_daemon(DEADLINE)
    host.refs[0].live = False
    assert not lease.current(DEADLINE)
    lease.close()


def test_receiver_must_have_its_own_full_id_cgroup(m, setup):
    collector, engine, host = setup
    old = host.cgroup
    def shared(process):
        result = old(process)
        result.path = '/shared-with-api'
        return result
    host.cgroup = shared
    with pytest.raises(m.IdentityError): collector.bind(NONCE, CID, DEADLINE)


@pytest.mark.parametrize('change', ['rootless', 'image', 'api_uid', 'api_namespace', 'deadline', 'engine_error'])
def test_untrusted_observations_fail_with_fixed_error_and_release_refs(m, setup, change):
    collector, engine, host = setup
    deadline = DEADLINE
    if change == 'rootless':
        engine.info = lambda deadline_ns: {'CgroupVersion': '2', 'SecurityOptions': ['name=rootless']}
    elif change == 'image':
        engine.receiver['Image'] = 'sha256:' + 'b' * 64
    elif change == 'api_uid':
        old = host.pin
        def pin(pid):
            result = old(pid)
            if pid == 22: result.uid = 2001
            return result
        host.pin = pin
    elif change == 'api_namespace':
        old = host.netns
        def ns(process):
            result = old(process)
            if process.pid == 22: result.inode += 1
            return result
        host.netns = ns
    elif change == 'deadline': deadline = 1
    else: engine.failed = True
    with pytest.raises(m.IdentityError, match='^identity_unverified$'):
        collector.bind(NONCE, CID, deadline)
    assert all(ref.closed for ref in host.refs)


def test_daemon_evidence_comes_from_systemd_instance_and_root_process(m, monkeypatch):
    import io
    from types import SimpleNamespace
    calls = []
    process = Process(111, 0)
    old_read = process.read
    process.read = lambda name: 'dockerd\n' if name == 'comm' else old_read(name)
    host = m._Host()
    host.pin = lambda pid: process if pid == 111 else None
    monkeypatch.setattr(m.os, 'geteuid', lambda: 0)
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout='MainPID=111\nInvocationID=' + 'a' * 32 + '\nActiveState=active\n')
    monkeypatch.setattr(m.subprocess, 'run', run)
    monkeypatch.setattr(m, 'open', lambda *a, **kw: io.StringIO('feedface-cafe-beef-feed-facecafebeef\n'), raising=False)
    result, invocation, boot = host.daemon(DEADLINE)
    assert result is process and invocation == 'a' * 32
    assert 'InvocationID' in calls[0][-1] and boot.endswith('facecafebeef')
    process.read = lambda name: 'not-dockerd\n' if name == 'comm' else old_read(name)
    with pytest.raises(m.IdentityError): host.daemon(DEADLINE)
    assert process.closed


@pytest.fixture
def deleted_group(m, monkeypatch, tmp_path, request):
    """Model retained kernel descriptors, not a pathname deletion heuristic."""
    import errno
    import os
    from types import SimpleNamespace
    for name in ('cgroup.events', 'cgroup.procs', 'cgroup.type'):
        (tmp_path / name).write_text('populated 1\n' if name == 'cgroup.events' else '')
    path = '/system.slice/docker-' + CID + '.scope'
    state = dict(link='/sys/fs/cgroup' + path, entries=[], error=errno.ENODEV,
                 core={}, bad_dir=False, bad_events=False, initial_bad=False,
                 list_error=False, seek_error=False, link_error=False,
                 release='6.17.0-1020-oracle')
    readlink, original_open, original_stat = m.os.readlink, m.os.open, m.os.fstat
    original_read, original_list, original_seek = m._read_fd, m.os.listdir, m.os.lseek
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.setattr(m.os, 'readlink', lambda name: state['link'] if name == '/proc/self/fd/' + str(fd) else readlink(name))
    if getattr(request, 'param', None) == 'initial_unverified': state['link'] = '/unverified/original'
    ref = m._Cgroup(fd, path)
    state['link'] = '/sys/fs/cgroup' + path + ' (deleted)'
    def stat(handle):
        value = original_stat(handle)
        mismatch = (handle == fd and state['bad_dir']) or (handle == ref.events_fd and state['bad_events'])
        return SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino + int(mismatch))
    def read(handle, limit=65536):
        if handle == ref.events_fd:
            raise OSError(state['error'], 'injected kernel observation')
        return original_read(handle, limit)
    def opened(name, flags, *, dir_fd=None):
        if dir_fd == fd and name in ('cgroup.events', 'cgroup.procs', 'cgroup.type'):
            number = state['core'].get(name, errno.ENOENT)
            if number:
                raise OSError(number, 'injected core-file observation')
        return original_open(name, flags, dir_fd=dir_fd)
    def listed(handle):
        if handle == fd:
            if state['list_error']: raise OSError(errno.EIO, 'injected directory observation')
            return list(state['entries'])
        return original_list(handle)
    def seek(handle, offset, how):
        if handle == fd and state['seek_error']: raise OSError(errno.EIO, 'injected seek observation')
        return original_seek(handle, offset, how)
    def linked(name):
        if state['link_error']: raise OSError(errno.EIO, 'injected procfd observation')
        assert name == '/proc/self/fd/' + str(fd), 'must query the retained descriptor only'
        return state['link']
    monkeypatch.setattr(m.os, 'fstat', stat)
    monkeypatch.setattr(m, '_read_fd', read)
    monkeypatch.setattr(m.os, 'open', opened)
    monkeypatch.setattr(m.os, 'listdir', listed)
    monkeypatch.setattr(m.os, 'lseek', seek)
    monkeypatch.setattr(m.os, 'readlink', linked)
    monkeypatch.setattr(m.os, 'uname', lambda: SimpleNamespace(release=state['release']))
    yield ref, state
    ref.close()


def test_deleted_original_cgroup_requires_the_complete_kernel_evidence(m, deleted_group):
    ref, state = deleted_group
    assert ref.tasks_remaining() == 0


@pytest.mark.parametrize('missing', [
    'enodev', 'dir_identity', 'events_identity', 'deleted_suffix', 'exact_path',
    'empty_directory', 'seek', 'list', 'procfd', 'reviewed_kernel',
    'cgroup.events_exists', 'cgroup.procs_exists', 'cgroup.type_exists',
    'cgroup.events_eacces', 'cgroup.procs_eio', 'cgroup.type_enodev'])
def test_each_missing_deleted_group_condition_stays_unknown(m, deleted_group, missing):
    import errno
    ref, state = deleted_group
    if missing == 'enodev': state['error'] = errno.EIO
    elif missing == 'dir_identity': state['bad_dir'] = True
    elif missing == 'events_identity': state['bad_events'] = True
    elif missing == 'deleted_suffix': state['link'] = state['link'].removesuffix(' (deleted)')
    elif missing == 'exact_path': state['link'] = '/sys/fs/cgroup/other.scope (deleted)'
    elif missing == 'empty_directory': state['entries'] = ['cgroup.procs']
    elif missing == 'seek': state['seek_error'] = True
    elif missing == 'list': state['list_error'] = True
    elif missing == 'procfd': state['link_error'] = True
    elif missing == 'reviewed_kernel': state['release'] = 'unreviewed-kernel'
    else:
        name, condition = missing.rsplit('_', 1)
        state['core'][name] = {'exists': 0, 'eacces': errno.EACCES, 'eio': errno.EIO, 'enodev': errno.ENODEV}[condition]
    assert ref.tasks_remaining() is None


@pytest.mark.parametrize('deleted_group', ['initial_unverified'], indirect=True)
def test_deleted_group_proof_needs_original_binding_path_verification(deleted_group):
    ref, state = deleted_group
    assert ref.tasks_remaining() is None


@pytest.mark.parametrize(('release', 'arch', 'signature', 'allowed'), [
    ('6.17.0-1020-oracle', 'aarch64', None, True),
    ('6.8.0-147-generic', 'aarch64', 'Ubuntu 6.8.0-147.147-generic 6.8.12\n', True),
    ('6.8.0-147-generic', 'aarch64', 'Ubuntu 6.8.0-147.148-generic 6.8.12\n', False),
    ('6.8.0-147-generic', 'aarch64', None, False),
    ('6.8.0-147-generic', 'x86_64', 'Ubuntu 6.8.0-147.147-generic 6.8.12\n', False),
    ('6.8.0-148-generic', 'aarch64', 'Ubuntu 6.8.0-147.147-generic 6.8.12\n', False),
])
def test_deleted_cgroup_kernel_is_bound_to_the_reviewed_build(m, monkeypatch, release, arch, signature, allowed):
    import io
    from types import SimpleNamespace

    monkeypatch.setattr(m.os, 'uname', lambda: SimpleNamespace(release=release, machine=arch))

    def read(path, *, encoding):
        assert path == '/proc/version_signature' and encoding == 'ascii'
        if signature is None:
            raise FileNotFoundError(path)
        return io.StringIO(signature)

    monkeypatch.setattr(m, 'open', read, raising=False)
    assert m._reviewed_deleted_cgroup_kernel() is allowed
