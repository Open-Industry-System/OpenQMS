"""Pinned-namespace nft and listener enforcement for the trusted management plane."""
import os
import select
import selectors
import subprocess
import time

from .contracts import DeploymentPermit
from .network import NetPolicy, build, parse_listing, verify


class NetworkError(ValueError):
    def __init__(self):
        super().__init__('network_invalid')


def _require(value):
    if not value:
        raise NetworkError()


def _command(fd, arguments, deadline_ns, data=None):
    """Only bounded trusted kernel metadata; receiver output never enters here."""
    _require(type(fd) is int and fd >= 0)
    _require(arguments in (('nft', '-j', 'list', 'ruleset'), ('nft', '-f', '-'),
                           ('ss', '-H', '-ltn'), ('ss', '-H', '-lun'), ('ss', '-H', '-lx')))
    _require(time.monotonic_ns() < deadline_ns)
    process = subprocess.Popen(
        ['nsenter', '--net=/proc/self/fd/%d' % fd, '--', *arguments],
        stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        pass_fds=(fd,), close_fds=True)
    output = bytearray()
    try:
        if data is not None:
            _require(type(data) is bytes and len(data) <= 4096)
            process.stdin.write(data)
            process.stdin.close()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = (deadline_ns - time.monotonic_ns()) / 10**9
                _require(remaining > 0)
                for key, _ in selector.select(min(remaining, .1)):
                    piece = os.read(key.fileobj.fileno(), 4096)
                    if not piece:
                        selector.unregister(key.fileobj)
                    else:
                        _require(len(output) + len(piece) <= 256 * 1024)
                        output.extend(piece)
        remaining = (deadline_ns - time.monotonic_ns()) / 10**9
        _require(remaining > 0)
        _require(process.wait(timeout=remaining) == 0)
        return bytes(output)
    except Exception:
        raise NetworkError() from None
    finally:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=.1)
        except subprocess.TimeoutExpired:
            # No success is reported. Kernel-uninterruptible processes remain
            # outside the design's hard-real-time guarantee. Do not wait forever.
            raise NetworkError() from None
        finally:
            process.stdout.close()


class NamespacePolicy:
    def __init__(self, netns_fd, permit, *, run=_command):
        _require(type(netns_fd) is int and netns_fd >= 0)
        _require(type(permit) is DeploymentPermit)
        self.netns_fd, self.permit, self.run = netns_fd, permit, run
        self.policy = NetPolicy(permit.api_uid, permit.receiver_uid, permit.api_port)

    def _listing(self, deadline_ns):
        return parse_listing(self.run(self.netns_fd, ('nft', '-j', 'list', 'ruleset'), deadline_ns))

    def install(self, deadline_ns):
        # Only an otherwise empty, newly owned namespace may be initialized.
        entries = self._listing(deadline_ns)['nftables']
        _require(all(type(entry) is dict and set(entry) == {'metainfo'} for entry in entries))
        self.run(self.netns_fd, ('nft', '-f', '-'), deadline_ns,
                 data=build(self.policy).text.encode('ascii'))
        _require(self.verify(deadline_ns))

    def verify(self, deadline_ns):
        try:
            listing = self._listing(deadline_ns)
            tables, chains, rules = [], [], []
            for entry in listing['nftables']:
                _require(type(entry) is dict and len(entry) == 1)
                kind, fact = next(iter(entry.items()))
                _require(kind in ('metainfo', 'table', 'chain', 'rule'))
                if kind == 'table': tables.append(fact)
                elif kind == 'chain': chains.append(fact)
                elif kind == 'rule': rules.append(fact)
            _require(len(tables) == 1 and tables[0].get('family') == 'inet'
                     and tables[0].get('name') == 'oqms4')
            _require(set(tables[0]) <= {'family', 'name', 'handle', 'flags'}
                     and not tables[0].get('flags'))
            _require(all(set(chain) <= {'family', 'table', 'name', 'handle', 'type',
                                        'hook', 'prio', 'policy'} for chain in chains))
            _require(len(chains) == 1 and len(rules) == 3)
            chain = chains[0]
            for key, expected in dict(family='inet', table='oqms4', name='output',
                                      type='filter', hook='output', prio=0, policy='drop').items():
                _require(chain.get(key) == expected)
            _require(all(rule.get('family') == 'inet' and rule.get('table') == 'oqms4'
                         and rule.get('chain') == 'output' for rule in rules))
            _require(verify(self.policy, listing).ok)
            tcp = self.run(self.netns_fd, ('ss', '-H', '-ltn'), deadline_ns).decode('ascii')
            rows = [line.split() for line in tcp.splitlines() if line.strip()]
            _require(len(rows) == 1 and len(rows[0]) >= 5)
            _require(rows[0][0] == 'LISTEN' and rows[0][3] == '127.0.0.1:%d' % self.permit.api_port)
            for kind in ('-lun', '-lx'):
                _require(not self.run(self.netns_fd, ('ss', '-H', kind), deadline_ns).strip())
            return True
        except Exception:
            return False


def _starttime(pid):
    with open('/proc/%d/stat' % pid, 'r') as handle:
        return int(handle.read(8192).rsplit(')', 1)[1].split()[19])


class APILease:
    """Live API pidfd/netns references, never reconstructed from persisted inode data."""
    def __init__(self, engine, manifest, deadline_ns):
        self.engine, self.manifest, self.deadline_ns = engine, manifest, deadline_ns
        self.pidfd = self.netns_fd = None
        try:
            self.permit = DeploymentPermit.from_mapping(manifest['permit'])
            self.api_id = manifest['api_container_id']
            raw = engine.inspect(self.api_id, deadline_ns=deadline_ns)
            _require(raw['Id'] == self.api_id and raw['State']['Running'] is True)
            _require(raw['Config']['User'] in (str(self.permit.api_uid),
                                               '%d:%d' % (self.permit.api_uid, self.permit.api_uid)))
            self.pid = raw['State']['Pid']
            _require(type(self.pid) is int and self.pid > 1)
            self.pidfd = os.pidfd_open(self.pid)
            self.start = _starttime(self.pid)
            with open('/proc/%d/uid_map' % self.pid) as handle:
                mappings = [tuple(map(int, row.split())) for row in handle.read(8192).splitlines()]
            _require(any(inside <= self.permit.api_uid < inside + size and outside == inside
                         for inside, outside, size in mappings))
            with open('/proc/%d/status' % self.pid) as handle:
                uids = next(row.split()[1:] for row in handle if row.startswith('Uid:'))
            _require(uids and all(int(uid) == self.permit.api_uid for uid in uids))
            self.netns_fd = os.open('/proc/%d/ns/net' % self.pid, os.O_RDONLY | os.O_CLOEXEC)
            self.boundary = NamespacePolicy(self.netns_fd, self.permit)
            _require(self._current(deadline_ns))
        except Exception:
            self.close()
            raise NetworkError() from None

    def _current(self, deadline_ns):
        if self.pidfd is None or select.select([self.pidfd], [], [], 0)[0]:
            return False
        raw = self.engine.inspect(self.api_id, deadline_ns=deadline_ns)
        return (raw['Id'] == self.api_id and raw['State']['Running'] is True
                and raw['State']['Pid'] == self.pid and _starttime(self.pid) == self.start
                and os.stat('/proc/%d/ns/net' % self.pid).st_ino == os.fstat(self.netns_fd).st_ino)

    def snapshot(self):
        fact = os.fstat(self.netns_fd)
        return dict(api_container_id=self.api_id, api_pid=self.pid, api_starttime=self.start,
                    netns_dev=fact.st_dev, netns_inode=fact.st_ino)

    def verify(self, deadline_ns=None):
        deadline_ns = self.deadline_ns if deadline_ns is None else deadline_ns
        try:
            return self._current(deadline_ns) and self.boundary.verify(deadline_ns)
        except Exception:
            return False

    def close(self):
        for name in ('pidfd', 'netns_fd'):
            fd = getattr(self, name, None)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)


def prepare_api(engine, manifest, deadline_ns, *, install=False):
    lease = APILease(engine, manifest, deadline_ns)
    try:
        if install and not lease.boundary.verify(deadline_ns):
            lease.boundary.install(deadline_ns)
        _require(lease.verify(deadline_ns))
        return lease
    except Exception:
        lease.close()
        raise NetworkError() from None
