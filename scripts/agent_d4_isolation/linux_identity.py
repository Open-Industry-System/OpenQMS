"""Trusted Linux observations and retained kernel capabilities for one receiver.

Snapshots are locators and historical facts, never kernel kill authority. Only a
live binding retains that authority. Failures expose one fixed diagnostic.
"""
import json
import errno
import os
import re
import secrets
import select
import subprocess
import time

from .cgroup import TerminationResult, UNKNOWN, VERIFIED
from .identity import KernelObject, ReceiverIdentity, UIDMap

SNAPSHOT_KEYS = frozenset(('version', 'nonce', 'container_id', 'image_id', 'api_container_id',
    'boot_id', 'daemon_invocation', 'daemon_pid', 'daemon_starttime',
    'receiver_pid', 'receiver_starttime', 'api_pid', 'api_starttime',
    'netns_dev', 'netns_inode', 'cgroup_dev', 'cgroup_inode', 'cgroup_path',
    'receiver_host_uid', 'api_host_uid'))


class IdentityError(ValueError):
    def __init__(self):
        super().__init__('identity_unverified')


def _require(ok):
    if not ok:
        raise IdentityError()


def _deadline(deadline_ns):
    _require(type(deadline_ns) is int and time.monotonic_ns() < deadline_ns)


def _recipe(nonce, image_id, api_container_id):
    from .linux_engine import recipe
    return recipe(nonce, image_id, api_container_id)


def _hex(value, length=64):
    return type(value) is str and re.fullmatch('[a-f0-9]{' + str(length) + '}', value) is not None


def _status(process):
    return dict(line.split(':', 1) for line in process.read('status').splitlines() if ':' in line)


def _uid(process, inside):
    matches = []
    for line in process.read('uid_map').splitlines():
        start, host, count = map(int, line.split())
        if start <= inside < start + count:
            matches.append(host + inside - start)
    _require(len(matches) == 1)
    actual = [int(x) for x in _status(process)['Uid'].split()]
    _require(actual == [matches[0]] * 4 and matches[0] > 0)
    return matches[0]


def _security_options(options):
    result = []
    for value in options or []:
        if value in ('no-new-privileges', 'no-new-privileges:true'):
            result.append(('nnp', True))
        elif value.startswith('seccomp='):
            result.append(('seccomp', json.dumps(json.loads(value[8:]), sort_keys=True, separators=(',', ':'))))
        else:
            result.append(('other', value))
    return sorted(result)


def _same_recipe(actual, expected):
    for key, value in expected.items():
        observed = actual.get(key)
        if key == 'SecurityOpt':
            _require(_security_options(observed) == _security_options(value))
        elif key == 'Ulimits':
            _require(sorted(observed or [], key=lambda x: x['Name']) == sorted(value, key=lambda x: x['Name']))
        elif value in ([], {}) and observed is None:
            continue                 # Engine normalises empty collections to null.
        else:
            _require(type(observed) is type(value) and observed == value)


def _verify_host_extras(host):
    for key in ('Devices', 'DeviceRequests', 'DeviceCgroupRules', 'GroupAdd',
                'VolumesFrom', 'Sysctls', 'Mounts', 'Links', 'PortBindings',
                'ExtraHosts', 'StorageOpt', 'LxcConf'):
        _require(not host.get(key))
    _require(host.get('Runtime', '') in ('', 'runc'))
    _require(host.get('OomKillDisable') in (None, False))


def _receiver_security(process):
    status = _status(process)
    _require(all(int(status[key].strip(), 16) == 0
                 for key in ('CapEff', 'CapPrm', 'CapBnd', 'CapInh', 'CapAmb')))
    _require(status['NoNewPrivs'].strip() == '1' and status['Seccomp'].strip() == '2')


def _dedicated_cgroup(cgroup, container_id):
    _require(cgroup.path.rsplit('/', 1)[-1] in (container_id, 'docker-' + container_id + '.scope'))


def _read_at(fd, name, limit=65536):
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        return _read_fd(child, limit)
    finally:
        os.close(child)


def _read_fd(fd, limit=65536):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks, size = [], 0
    while True:
        raw = os.read(fd, min(4096, limit + 1 - size))
        if not raw:
            return b''.join(chunks).decode('ascii')
        chunks.append(raw)
        size += len(raw)
        _require(size <= limit)


def _starttime(stat):
    try:
        result = int(stat[stat.rindex(')') + 2:].split()[19])
        _require(result > 0)
        return result
    except (ValueError, IndexError):
        raise IdentityError() from None


class _Process:
    def __init__(self, pid):
        _require(type(pid) is int and pid > 0)
        self.pid, self.fd, self.pidfd = pid, None, None
        try:
            self.fd = os.open('/proc/' + str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.starttime = _starttime(self.read('stat'))
            self.pidfd = os.pidfd_open(pid, 0)
            _require(self.alive())
        except Exception:
            self.close()
            raise

    def read(self, name):
        return _read_at(self.fd, name)

    def alive(self):
        try:
            if self.pidfd is None or self.fd is None:
                return False
            poll = select.poll()
            poll.register(self.pidfd, select.POLLIN | select.POLLHUP | select.POLLERR)
            return not poll.poll(0) and _starttime(self.read('stat')) == self.starttime
        except (OSError, ValueError):
            return False

    def close(self):
        for name in ('pidfd', 'fd'):
            fd = getattr(self, name, None)
            if fd is not None:
                setattr(self, name, None)
                os.close(fd)


class _Namespace:
    def __init__(self, fd):
        self.fd = fd
        fact = os.fstat(fd)
        self.device, self.inode = fact.st_dev, fact.st_ino

    def alive(self):
        try:
            fact = os.fstat(self.fd)
            return (fact.st_dev, fact.st_ino) == (self.device, self.inode)
        except (OSError, TypeError):
            return False

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


def _reviewed_deleted_cgroup_kernel():
    kernel = os.uname()
    if kernel.release == '6.17.0-1020-oracle':
        return True
    if (kernel.release, kernel.machine) != ('6.8.0-147-generic', 'aarch64'):
        return False
    try:
        with open('/proc/version_signature', encoding='ascii') as stream:
            return stream.read(128) == 'Ubuntu 6.8.0-147.147-generic 6.8.12\n'
    except (OSError, UnicodeError):
        return False


class _Cgroup(_Namespace):
    def __init__(self, fd, path):
        super().__init__(fd)
        self.path, self.events_fd = path, None
        self._initial_fd_path = None
        try:
            self.events_fd = os.open('cgroup.events', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            events = os.fstat(self.events_fd)
            self._events_identity = (events.st_dev, events.st_ino)
            try:
                current = os.readlink('/proc/self/fd/' + str(fd))
                if current == '/sys/fs/cgroup' + path:
                    self._initial_fd_path = current
            except OSError:
                pass
        except Exception:
            self.close()
            raise

    def read(self, name):
        return _read_at(self.fd, name)

    def tasks_remaining(self):
        try:
            _require(self.alive())
            try:
                raw = _read_fd(self.events_fd)
            except OSError as error:
                if error.errno == errno.ENODEV and self._deleted_empty():
                    return 0
                return None
            events = dict(line.split() for line in raw.splitlines())
            _require(events.get('populated') in ('0', '1'))
            if events['populated'] == '0':
                # Kernel populated covers the complete descendant subtree; this
                # descriptor is continuous; removal may instead yield ENODEV.
                return 0
            count = self._count(self.fd)
            return count if count > 0 else None
        except Exception:
            return None

    def _deleted_empty(self):
        """Empty original object proof, not permission to reopen a saved path.

        Bound and observed on the reviewed Ubuntu Oracle and Lima builds. In upstream v6.17,
        cgroup_destroy_locked rejects populated/online children, prevents further
        migration/creation, then removes the core files and directory:
        https://github.com/torvalds/linux/blob/v6.17/kernel/cgroup/cgroup.c#L5679-L5720
        ENODEV alone is insufficient; kernfs getattr also refreshes nlink to 2:
        https://github.com/torvalds/linux/blob/v6.17/fs/kernfs/inode.c#L157-L186
        d_path appends the marker for the retained FD's unlinked dentry:
        https://github.com/torvalds/linux/blob/v6.17/fs/d_path.c#L268-L275
        """
        try:
            _require(_reviewed_deleted_cgroup_kernel())
            _require(self._initial_fd_path is not None and self.alive())
            events = os.fstat(self.events_fd)
            _require((events.st_dev, events.st_ino) == self._events_identity)
            _require(os.readlink('/proc/self/fd/' + str(self.fd)) == self._initial_fd_path + ' (deleted)')
            os.lseek(self.fd, 0, os.SEEK_SET)
            _require(os.listdir(self.fd) == [])
            for name in ('cgroup.events', 'cgroup.procs', 'cgroup.type'):
                try:
                    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
                except OSError as error:
                    _require(error.errno == errno.ENOENT)
                else:
                    os.close(child)
                    return False
            events = os.fstat(self.events_fd)
            return self.alive() and (events.st_dev, events.st_ino) == self._events_identity
        except Exception:
            return False

    @staticmethod
    def _count(fd):
        result = len(_read_at(fd, 'cgroup.procs').split())
        for name in os.listdir(fd):
            try:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except NotADirectoryError:
                continue
            try:
                result += _Cgroup._count(child)
            finally:
                os.close(child)
        return result

    def kill(self):
        _require(self.alive())
        fd = os.open('cgroup.kill', os.O_WRONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            _require(os.write(fd, b'1') == 1)
        finally:
            os.close(fd)

    def close(self):
        events = getattr(self, 'events_fd', None)
        if events is not None:
            self.events_fd = None
            os.close(events)
        super().close()


class _Host:
    def daemon(self, deadline_ns):
        _deadline(deadline_ns)
        _require(os.geteuid() == 0)
        result = subprocess.run(['/usr/bin/systemctl', 'show', 'docker.service',
            '--property=MainPID,InvocationID,ActiveState'], capture_output=True, text=True,
            timeout=max(.001, (deadline_ns - time.monotonic_ns()) / 10**9), check=True)
        values = dict(line.split('=', 1) for line in result.stdout.splitlines())
        _require(values['ActiveState'] == 'active' and _hex(values['InvocationID'], 32))
        process = self.pin(int(values['MainPID']))
        try:
            _require(process.read('comm').strip() == 'dockerd')
            _require([int(x) for x in _status(process)['Uid'].split()] == [0, 0, 0, 0])
            with open('/proc/sys/kernel/random/boot_id', encoding='ascii') as source:
                boot = source.read(64).strip()
            _require(re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', boot) is not None)
            return process, values['InvocationID'], boot
        except Exception:
            process.close()
            raise

    def pin(self, pid):
        return _Process(pid)

    def netns(self, process):
        # This is the fixed kernel nsfs link beneath a retained /proc directory,
        # not a user-supplied symlink or a historical namespace path.
        return _Namespace(os.open('ns/net', os.O_RDONLY, dir_fd=process.fd))

    def cgroup(self, process):
        lines = process.read('cgroup').splitlines()
        _require(len(lines) == 1 and lines[0].startswith('0::/'))
        path = lines[0][3:]
        components = path.split('/')[1:]
        _require(bool(components) and all(x not in ('', '.', '..') for x in components))
        fd = os.open('/sys/fs/cgroup', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in components:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            _require(str(process.pid) in _read_at(fd, 'cgroup.procs').split())
            owned, fd = fd, None
            result = _Cgroup(owned, path)
            return result
        finally:
            if fd is not None:
                os.close(fd)

    def verify_limits(self, process, cgroup):
        _require(cgroup.read('memory.max').strip() == '134217728')
        _require(cgroup.read('memory.swap.max').strip() == '0')
        _require(cgroup.read('pids.max').strip() == '16')
        quota, period = map(int, cgroup.read('cpu.max').split())
        _require(quota == period and quota > 0)
        limits = process.read('limits')
        for label, expected in (('Max open files', '64'), ('Max core file size', '0')):
            line = next(x for x in limits.splitlines() if x.startswith(label))
            _require(line[len(label):].split()[:2] == [expected, expected])
        mounts = [line.split() for line in process.read('mountinfo').splitlines()]
        root = next(x for x in mounts if x[4] == '/')
        _require('ro' in root[5].split(','))
        tmp = next(x for x in mounts if x[4] == '/tmp')
        separator = tmp.index('-')
        options = set(tmp[5].split(',')) | set(tmp[separator + 3].split(','))
        _require(tmp[separator + 1] == 'tmpfs')
        _require({'nodev', 'nosuid', 'noexec', 'size=8192k', 'nr_inodes=128'} <= options)


class KernelCollector:
    def __init__(self, engine, image_id, api_container_id):
        _require(type(image_id) is str and re.fullmatch(r'sha256:[a-f0-9]{64}', image_id) is not None)
        _require(_hex(api_container_id))
        self.engine, self.image_id, self.api_container_id = engine, image_id, api_container_id
        self.host = _Host()

    def pin_daemon(self, deadline_ns):
        process = None
        try:
            _deadline(deadline_ns)
            process, invocation, boot = self.host.daemon(deadline_ns)
            _require(process.alive())
            _deadline(deadline_ns)
            return DaemonLease(self.host, process, invocation, boot)
        except Exception:
            if process is not None:
                process.close()
            raise IdentityError() from None

    def _verified_inspect(self, nonce, container_id, deadline_ns):
        _deadline(deadline_ns)
        _require(_hex(nonce) and _hex(container_id) and container_id != self.api_container_id)
        info = self.engine.info(deadline_ns)
        _require(info['CgroupVersion'] == '2')
        _require(not any('rootless' in x.lower() for x in info['SecurityOptions']))
        image = self.engine.inspect_image(self.image_id, deadline_ns)
        _require(image['Id'] == self.image_id)
        expected = _recipe(nonce, self.image_id, self.api_container_id)
        _require(image['Config']['User'] == expected['User'])
        _require(image['Config']['Entrypoint'] == expected['Entrypoint'])
        receiver = self.engine.inspect(container_id, deadline_ns)
        _require(receiver['Id'] == container_id and receiver['Image'] == self.image_id)
        config = {k: v for k, v in expected.items() if k != 'HostConfig'}
        # Engine merges the frozen image's environment into empty create Env.
        # Only that byte-for-byte baseline is permitted; it never enters state.
        config['Env'] = image['Config'].get('Env') or []
        _same_recipe(receiver['Config'], config)
        _same_recipe(receiver['HostConfig'], expected['HostConfig'])
        _verify_host_extras(receiver['HostConfig'])
        _require(all(x.get('Type') == 'tmpfs' and x.get('Destination') == '/tmp' for x in receiver.get('Mounts', [])))
        return receiver

    def verify_created(self, nonce, container_id, deadline_ns):
        """A current exact never-started recipe; not proof create has converged."""
        daemon = None
        try:
            receiver = self._verified_inspect(nonce, container_id, deadline_ns)
            state = receiver['State']
            _require(state['Status'] == 'created' and type(state['Pid']) is int and state['Pid'] == 0)
            _require(state['Running'] is False and state.get('Restarting') is False)
            daemon, _, _ = self.host.daemon(deadline_ns)
            _require(daemon.alive())
            _deadline(deadline_ns)
            return True
        except Exception:
            return False
        finally:
            if daemon is not None:
                daemon.close()

    def bind(self, nonce, container_id, deadline_ns):
        refs = []
        try:
            receiver = self._verified_inspect(nonce, container_id, deadline_ns)
            api = self.engine.inspect(self.api_container_id, deadline_ns)
            _require(api['Id'] == self.api_container_id and api['Config']['User'] == '2002:2002')
            _require(receiver['State']['Running'] is True and api['State']['Running'] is True)
            daemon, invocation, boot = self.host.daemon(deadline_ns)
            refs.append(daemon)
            process = self.host.pin(receiver['State']['Pid']); refs.append(process)
            api_process = self.host.pin(api['State']['Pid']); refs.append(api_process)
            netns = self.host.netns(process); refs.append(netns)
            api_netns = self.host.netns(api_process); refs.append(api_netns)
            cgroup = self.host.cgroup(process); refs.append(cgroup)
            _dedicated_cgroup(cgroup, container_id)
            _require((netns.device, netns.inode) == (api_netns.device, api_netns.inode))
            receiver_uid, api_uid = _uid(process, 2001), _uid(api_process, 2002)
            _require(receiver_uid != api_uid)
            _receiver_security(process)
            self.host.verify_limits(process, cgroup)
            _require(all(x.alive() for x in refs))
            _deadline(deadline_ns)
            snapshot = dict(version=1, nonce=nonce, container_id=container_id,
                image_id=self.image_id, api_container_id=self.api_container_id,
                boot_id=boot, daemon_invocation=invocation, daemon_pid=daemon.pid,
                daemon_starttime=daemon.starttime, receiver_pid=process.pid,
                receiver_starttime=process.starttime, api_pid=api_process.pid,
                api_starttime=api_process.starttime, netns_dev=netns.device,
                netns_inode=netns.inode, cgroup_dev=cgroup.device, cgroup_inode=cgroup.inode,
                cgroup_path=cgroup.path, receiver_host_uid=receiver_uid, api_host_uid=api_uid)
            return LiveBinding(self, snapshot, refs, process, cgroup, netns)
        except Exception:
            for ref in reversed(refs):
                ref.close()
            raise IdentityError() from None

    def _bind_reclaim(self, snapshot, deadline_ns):
        """Current receiver proof only; API may have failed, forbidding delivery."""
        refs = []
        try:
            s = snapshot
            receiver = self._verified_inspect(s['nonce'], s['container_id'], deadline_ns)
            _require(receiver['State']['Running'] is True)
            daemon, invocation, boot = self.host.daemon(deadline_ns); refs.append(daemon)
            _require((daemon.pid, daemon.starttime, invocation, boot) ==
                     (s['daemon_pid'], s['daemon_starttime'], s['daemon_invocation'], s['boot_id']))
            process = self.host.pin(receiver['State']['Pid']); refs.append(process)
            _require((process.pid, process.starttime) == (s['receiver_pid'], s['receiver_starttime']))
            netns = self.host.netns(process); refs.append(netns)
            cgroup = self.host.cgroup(process); refs.append(cgroup)
            _dedicated_cgroup(cgroup, s['container_id'])
            _require((netns.device, netns.inode) == (s['netns_dev'], s['netns_inode']))
            _require((cgroup.device, cgroup.inode, cgroup.path) ==
                     (s['cgroup_dev'], s['cgroup_inode'], s['cgroup_path']))
            _require(_uid(process, 2001) == s['receiver_host_uid'])
            _receiver_security(process)
            self.host.verify_limits(process, cgroup)
            _require(all(x.alive() for x in refs))
            _deadline(deadline_ns)
            binding = LiveBinding(self, dict(s), refs, process, cgroup, netns)
            binding._allow_kernel = False
            binding._reclaim_only = True
            return binding
        except Exception:
            for ref in reversed(refs):
                ref.close()
            raise IdentityError() from None

    def revalidate(self, binding, deadline_ns, delivery=True):
        current = None
        try:
            _require(binding.collector is self and not binding.closed)
            _require(all(x.alive() for x in binding.refs))
            _require(not (delivery and binding._reclaim_only))
            current = (self.bind(binding._snapshot['nonce'], binding._snapshot['container_id'], deadline_ns)
                       if delivery else self._bind_reclaim(binding._snapshot, deadline_ns))
            _require(current._snapshot == binding._snapshot)
            return binding.identity()
        except Exception:
            return None
        finally:
            if current is not None:
                current.close()


class DaemonLease:
    """Retain daemon generation before any create side effect is possible."""
    def __init__(self, host, process, invocation, boot):
        self.host, self.process = host, process
        self.closed, self.invalidated = False, False
        self._snapshot = dict(boot_id=boot, daemon_invocation=invocation,
                              daemon_pid=process.pid, daemon_starttime=process.starttime)

    def snapshot(self):
        return dict(self._snapshot)

    def current(self, deadline_ns):
        process = None
        try:
            _deadline(deadline_ns)
            _require(not self.closed and not self.invalidated and self.process.alive())
            process, invocation, boot = self.host.daemon(deadline_ns)
            s = self._snapshot
            _require(process.alive() and (process.pid, process.starttime, invocation, boot) ==
                     (s['daemon_pid'], s['daemon_starttime'], s['daemon_invocation'], s['boot_id']))
            _deadline(deadline_ns)
            return True
        except Exception:
            self.invalidated = True
            return False
        finally:
            if process is not None:
                process.close()

    def close(self):
        if not self.closed:
            self.closed = True
            self.process.close()


class LiveBinding:
    def __init__(self, collector, snapshot, refs, process, cgroup, netns):
        self.collector, self._snapshot, self.refs = collector, snapshot, refs
        self.process, self.cgroup, self.netns = process, cgroup, netns
        self.closed, self._allow_kernel = False, True
        self._reclaim_only = False
        self._net_token, self._cg_token = secrets.token_bytes(32), secrets.token_bytes(32)

    def snapshot(self):
        return dict(self._snapshot)

    @property
    def netns_fd(self):
        return None if self.closed else self.netns.fd

    @property
    def receiver_pid(self):
        return self._snapshot['receiver_pid']

    @property
    def api_pid(self):
        return self._snapshot['api_pid']

    def identity(self):
        s = self._snapshot
        return ReceiverIdentity(s['boot_id'] + ':' + s['daemon_invocation'] + ':' + str(s['daemon_starttime']),
            s['container_id'], s['nonce'], s['image_id'],
            KernelObject(self.netns.device, self.netns.inode, self._net_token),
            UIDMap(2001, s['receiver_host_uid'], 1),
            KernelObject(self.cgroup.device, self.cgroup.inode, self._cg_token))

    def close(self):
        if not self.closed:
            self.closed = True
            for ref in reversed(self.refs):
                ref.close()

    def signal(self, signal, deadline_ns):
        if signal not in ('SIGTERM', 'SIGKILL'):
            return False
        if self.collector.revalidate(self, deadline_ns, delivery=False) is None:
            return False
        try:
            self.collector.engine.signal(self._snapshot['container_id'], signal, deadline_ns)
            return True
        except Exception:
            return False

    def tasks_remaining(self):
        if self.closed:
            return None
        return self.cgroup.tasks_remaining()

    def terminate(self, deadline_ns=None):
        deadline_ns = deadline_ns if deadline_ns is not None else time.monotonic_ns() + 5 * 10**9
        try:
            _deadline(deadline_ns)
            _require(not self.closed and self._allow_kernel and self.cgroup.alive())
            if self.tasks_remaining() == 0:
                return TerminationResult(True, VERIFIED)
            self.cgroup.kill()
            while time.monotonic_ns() < deadline_ns:
                if self.tasks_remaining() == 0:
                    return TerminationResult(True, VERIFIED)
                time.sleep(min(.05, max(0, (deadline_ns - time.monotonic_ns()) / 10**9)))
        except Exception:
            pass
        return TerminationResult(False, UNKNOWN)

    def container_running(self, deadline_ns):
        daemon = None
        try:
            _require(not self.closed)
            daemon, invocation, boot = self.collector.host.daemon(deadline_ns)
            s = self._snapshot
            _require((daemon.pid, daemon.starttime, invocation, boot) ==
                     (s['daemon_pid'], s['daemon_starttime'], s['daemon_invocation'], s['boot_id']))
            current = self.collector.engine.inspect(s['container_id'], deadline_ns)
            _require(current['Id'] == s['container_id'] and current['Image'] == s['image_id'])
            _require(current['Config']['Labels'] == _recipe(s['nonce'], s['image_id'], s['api_container_id'])['Labels'])
            _require(type(current['State']['Running']) is bool)
            _deadline(deadline_ns)
            return current['State']['Running']
        except Exception:
            return None
        finally:
            if daemon is not None:
                daemon.close()


def fresh_stop_binding(snapshot, nonce, deadline_ns, *, engine=None):
    """Reacquire current Engine authority; never restore historical kernel kill."""
    binding = None
    try:
        _require(type(snapshot) is dict and set(snapshot) == SNAPSHOT_KEYS)
        _require(type(snapshot['version']) is int and snapshot['version'] == 1 and snapshot['nonce'] == nonce)
        integer_keys = ('daemon_pid', 'daemon_starttime', 'receiver_pid', 'receiver_starttime',
                        'api_pid', 'api_starttime', 'netns_inode', 'cgroup_inode',
                        'receiver_host_uid', 'api_host_uid')
        _require(all(type(snapshot[key]) is int and snapshot[key] > 0 for key in integer_keys))
        _require(all(type(snapshot[key]) is int and snapshot[key] >= 0 for key in ('netns_dev', 'cgroup_dev')))
        if engine is None:
            from .linux_engine import EngineClient
            engine = EngineClient()
        collector = KernelCollector(engine, snapshot['image_id'], snapshot['api_container_id'])
        binding = collector._bind_reclaim(snapshot, deadline_ns)
        _require(binding.snapshot() == snapshot)
        binding._allow_kernel = False
        return binding
    except Exception:
        if binding is not None:
            binding.close()
        return None
