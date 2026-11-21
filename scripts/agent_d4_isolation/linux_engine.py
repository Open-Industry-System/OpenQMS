"""Bounded stdlib Unix-socket Docker Engine adapter for the frozen receiver.

Raw trusted inspect dictionaries remain inside the privileged runtime. Errors
carry only fixed codes; HTTP response text is never included in diagnostics.
No operation accepts a command, URL, mount, or caller-supplied HostConfig.
"""
import json
import re
import socket
import struct
import time
from urllib.parse import urlencode

from .contracts import RECEIVER_ENTRYPOINT
from .docker_api import TransportError

NONCE_LABEL = 'org.openqms.d4.nonce'
API_VERSION = '/v1.45'
HEADER_LIMIT = 16384
BODY_LIMIT = 262144
CHUNK = 512
ERROR_CODES = ('engine_invalid', 'engine_protocol', 'engine_deadline',
               'engine_unavailable', 'engine_not_found', 'engine_status',
               'engine_attach_used')


class EngineError(TransportError):
    def __init__(self, code='engine_invalid'):
        super().__init__(code if code in ERROR_CODES else 'engine_invalid')


def _require(value, code='engine_invalid'):
    if not value:
        raise EngineError(code)


def _id(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None


def _image(value):
    return type(value) is str and re.fullmatch('sha256:[a-f0-9]{64}', value) is not None


def _unique(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, 'engine_protocol')
        value[key] = item
    return value


def _loads(raw):
    result = None
    try:
        result = json.loads(raw, object_pairs_hook=_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        pass
    _require(result is not None, 'engine_protocol')
    return result


# Python stdlib startup/file/HTTP operations only. Default-deny excludes process
# creation, namespace/credential changes, bind/listen, ptrace/mount/bpf, and
# AF_UNIX/netlink/raw sockets. Real-host normal/attack validation is mandatory.
_SYSCALLS = '''read write readv writev close close_range stat fstat lstat newfstatat statx
lseek pread64 pwrite64 open openat access faccessat faccessat2 readlink readlinkat
getdents64 fcntl ioctl dup dup2 dup3 pipe pipe2 poll ppoll select pselect6
mmap mmap2 mprotect munmap mremap madvise brk rt_sigaction rt_sigprocmask
rt_sigreturn sigaltstack restart_syscall futex futex_waitv set_tid_address
set_robust_list rseq arch_prctl prlimit64 getrlimit getrusage sysinfo
clock_gettime clock_gettime64 clock_nanosleep clock_nanosleep_time64 nanosleep
gettimeofday time times getpid getppid gettid getuid geteuid getgid getegid
getgroups uname getcwd chdir fchdir getrandom sched_getaffinity sched_yield
exit exit_group execve connect getsockname getpeername getsockopt setsockopt
sendto recvfrom sendmsg recvmsg shutdown fsync fdatasync ftruncate truncate
mkdir mkdirat rmdir unlink unlinkat rename renameat renameat2 chmod fchmod
fchmodat umask statfs fstatfs utimensat epoll_create1 epoll_ctl epoll_wait
 epoll_pwait epoll_pwait2 eventfd2 membarrier'''.split()
SECCOMP_PROFILE = {
    'defaultAction': 'SCMP_ACT_ERRNO',
    'defaultErrnoRet': 1,
    'architectures': ['SCMP_ARCH_X86_64', 'SCMP_ARCH_AARCH64'],
    'syscalls': [
        {'names': _SYSCALLS, 'action': 'SCMP_ACT_ALLOW'},
        {'names': ['socket'], 'action': 'SCMP_ACT_ALLOW', 'args': [
            {'index': 0, 'value': 2, 'op': 'SCMP_CMP_EQ'},
            {'index': 1, 'value': 15, 'valueTwo': 1, 'op': 'SCMP_CMP_MASKED_EQ'},
            {'index': 2, 'value': 0, 'op': 'SCMP_CMP_EQ'}]},
        {'names': ['socket'], 'action': 'SCMP_ACT_ALLOW', 'args': [
            {'index': 0, 'value': 2, 'op': 'SCMP_CMP_EQ'},
            {'index': 1, 'value': 15, 'valueTwo': 1, 'op': 'SCMP_CMP_MASKED_EQ'},
            {'index': 2, 'value': 6, 'op': 'SCMP_CMP_EQ'}]},
    ]}


def recipe(nonce, image_id, api_container_id):
    """Return a fresh fixed create body; all arguments are immutable identities."""
    _require(_id(nonce) and _image(image_id) and _id(api_container_id))
    return {
        'Image': image_id, 'User': '2001:2001',
        'Entrypoint': list(RECEIVER_ENTRYPOINT), 'Cmd': [], 'Env': [],
        'WorkingDir': '/', 'Labels': {NONCE_LABEL: nonce}, 'Volumes': {},
        'Tty': False, 'OpenStdin': True, 'StdinOnce': True,
        'AttachStdin': True, 'AttachStdout': True, 'AttachStderr': True,
        'HostConfig': {
            'NetworkMode': 'container:' + api_container_id,
            'IpcMode': 'none', 'PidMode': '', 'UTSMode': '',
            'CgroupnsMode': 'private', 'UsernsMode': 'host',
            'Privileged': False, 'ReadonlyRootfs': True,
            'CapDrop': ['ALL'], 'CapAdd': [], 'Binds': [],
            'SecurityOpt': ['no-new-privileges:true', 'seccomp=' + json.dumps(
                SECCOMP_PROFILE, sort_keys=True, separators=(',', ':'))],
            'Memory': 128 * 1024 * 1024, 'MemorySwap': 128 * 1024 * 1024,
            'NanoCpus': 10**9, 'PidsLimit': 16,
            'Ulimits': [{'Name': 'nofile', 'Soft': 64, 'Hard': 64},
                        {'Name': 'core', 'Soft': 0, 'Hard': 0}],
            'Tmpfs': {'/tmp': 'rw,nodev,nosuid,noexec,size=8m,nr_inodes=128'},
            'LogConfig': {'Type': 'none', 'Config': {}},
            'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
            'AutoRemove': False, 'PublishAllPorts': False,
        }}


class _Wire:
    def __init__(self, sock, clock, pending=b''):
        self.sock, self.clock, self.pending = sock, clock, pending

    def remaining(self, deadline_ns):
        _require(type(deadline_ns) is int and deadline_ns > 0)
        remaining = deadline_ns - self.clock()
        _require(remaining > 0, 'engine_deadline')
        self.sock.settimeout(remaining / 10**9)

    def send(self, value, deadline_ns):
        self.remaining(deadline_ns)
        sent = self.sock.send(value)
        _require(type(sent) is int and 0 < sent <= len(value), 'engine_protocol')
        self.remaining(deadline_ns)
        return sent

    def receive(self, size, deadline_ns):
        self.remaining(deadline_ns)
        if self.pending:
            value, self.pending = self.pending[:size], self.pending[size:]
            return value
        value = self.sock.recv(size)
        self.remaining(deadline_ns)
        return value

    def line(self, deadline_ns, limit=HEADER_LIMIT):
        value = bytearray()
        while not value.endswith(b'\r\n'):
            _require(len(value) < limit, 'engine_protocol')
            value.extend(self.exact(1, deadline_ns))
        return bytes(value[:-2])

    def exact(self, size, deadline_ns, *, eof=False):
        # Callers request at most one bounded frame/header fragment.
        value = bytearray()
        while len(value) < size:
            piece = self.receive(size - len(value), deadline_ns)
            if not piece:
                if eof and not value:
                    return b''
                raise EngineError('engine_protocol')
            value.extend(piece)
        return bytes(value)


class AttachedIO:
    """Single raw attach stream. Neither frame lengths nor output are buffered."""
    def __init__(self, wire):
        self._wire = wire
        self._stdin_closed = False
        self._closed = False
        self._reading = False

    def write(self, data, deadline_ns):
        _require(not self._closed and not self._stdin_closed and type(data) is bytes and data)
        try:
            return self._wire.send(data, deadline_ns)
        except EngineError:
            raise
        except (OSError, TimeoutError):
            raise EngineError('engine_unavailable') from None

    def close_stdin(self):
        if not self._stdin_closed and not self._closed:
            self._stdin_closed = True
            try:
                self._wire.sock.shutdown(socket.SHUT_WR)
            except OSError:
                raise EngineError('engine_unavailable') from None

    def chunks(self, deadline_ns):
        _require(not self._closed and not self._reading)
        self._reading = True
        try:
            while True:
                head = self._wire.exact(8, deadline_ns, eof=True)
                if not head:
                    return
                _require(head[0] in (1, 2) and head[1:4] == b'\0\0\0', 'engine_protocol')
                length = struct.unpack('>I', head[4:])[0]
                while length:
                    value = self._wire.exact(min(CHUNK, length), deadline_ns)
                    length -= len(value)
                    yield value
        except EngineError:
            raise
        except (OSError, TimeoutError):
            raise EngineError('engine_unavailable') from None

    def close(self):
        if not self._closed:
            self._closed = True
            self._wire.sock.close()


class EngineClient:
    def __init__(self, socket_path='/var/run/docker.sock', *, clock=time.monotonic_ns):
        _require(type(socket_path) is str and socket_path.startswith('/') and
                 '\0' not in socket_path and '..' not in socket_path.split('/'))
        _require(callable(clock))
        self._socket_path, self._clock = socket_path, clock

    def _request(self, method, path, deadline_ns, *, body=None, statuses=(200,), upgrade=False):
        sock = None
        transferred = False
        try:
            _require(type(deadline_ns) is int and deadline_ns > self._clock(), 'engine_deadline')
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            wire = _Wire(sock, self._clock)
            wire.remaining(deadline_ns)
            sock.connect(self._socket_path)
            raw = b'' if body is None else json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            headers = ('%s %s%s HTTP/1.1\r\nHost: localhost\r\nContent-Length: %d\r\nContent-Type: application/json\r\n'
                       % (method, API_VERSION, path, len(raw))).encode()
            headers += b'Connection: Upgrade\r\nUpgrade: tcp\r\n\r\n' if upgrade else b'Connection: close\r\n\r\n'
            outgoing = headers + raw
            offset = 0
            while offset < len(outgoing):
                offset += wire.send(memoryview(outgoing)[offset:], deadline_ns)
            head = bytearray()
            while b'\r\n\r\n' not in head:
                _require(len(head) < HEADER_LIMIT, 'engine_protocol')
                piece = wire.receive(min(CHUNK, HEADER_LIMIT - len(head)), deadline_ns)
                _require(piece, 'engine_protocol')
                head.extend(piece)
            header, pending = bytes(head).split(b'\r\n\r\n', 1)
            wire.pending = pending
            lines = header.split(b'\r\n')
            match = re.fullmatch(rb'HTTP/1\.[01] ([0-9]{3})(?: [\x20-\x7e]*)?', lines[0])
            _require(match is not None, 'engine_protocol')
            status = int(match[1])
            _require(status != 404, 'engine_not_found')
            _require(status in statuses, 'engine_status')
            parsed = {}
            for line in lines[1:]:
                _require(b':' in line and not line.startswith((b' ', b'\t')), 'engine_protocol')
                key, value = line.split(b':', 1)
                _require(re.fullmatch(rb'[!#$%&\x27*+.^_`|~0-9A-Za-z-]+', key), 'engine_protocol')
                key, value = key.lower(), value.strip()
                _require(key not in parsed and not any(x < 32 or x > 126 for x in value), 'engine_protocol')
                parsed[key] = value
            _require(not (b'content-length' in parsed and b'transfer-encoding' in parsed), 'engine_protocol')
            if upgrade:
                _require(b'transfer-encoding' not in parsed, 'engine_protocol')
                if status == 101:
                    _require(parsed.get(b'upgrade', b'').lower() == b'tcp' and
                             b'upgrade' in parsed.get(b'connection', b'').lower().split(b','), 'engine_protocol')
                transferred = True
                return AttachedIO(wire)
            if status == 204:
                _require(not pending and b'transfer-encoding' not in parsed and
                         parsed.get(b'content-length', b'0') == b'0', 'engine_protocol')
                wire.remaining(deadline_ns)
                return b''
            if b'transfer-encoding' in parsed:
                _require(parsed[b'transfer-encoding'].lower() == b'chunked', 'engine_protocol')
                result = bytearray()
                while True:
                    chunk_header = wire.line(deadline_ns, 128)
                    _require(re.fullmatch(rb'[0-9a-fA-F]{1,8}', chunk_header) is not None, 'engine_protocol')
                    chunk_size = int(chunk_header, 16)
                    _require(len(result) + chunk_size <= BODY_LIMIT, 'engine_protocol')
                    if chunk_size == 0:
                        # This fixed Engine API sends no HTTP trailers.
                        _require(wire.line(deadline_ns) == b'' and not wire.pending, 'engine_protocol')
                        wire.remaining(deadline_ns)
                        return bytes(result)
                    left = chunk_size
                    while left:
                        piece = wire.exact(min(CHUNK, left), deadline_ns)
                        result.extend(piece)
                        left -= len(piece)
                    _require(wire.exact(2, deadline_ns) == b'\r\n', 'engine_protocol')
            length = parsed.get(b'content-length', b'')
            _require(re.fullmatch(rb'[0-9]{1,9}', length) is not None, 'engine_protocol')
            size = int(length)
            _require(size <= BODY_LIMIT, 'engine_protocol')
            _require(len(pending) <= size, 'engine_protocol')
            # The complete ordinary Engine response is bounded by BODY_LIMIT.
            result = bytearray()
            while len(result) < size:
                result.extend(wire.exact(min(CHUNK, size - len(result)), deadline_ns))
            wire.remaining(deadline_ns)
            return bytes(result)
        except EngineError:
            raise
        except (OSError, TimeoutError, ValueError, TypeError, OverflowError):
            raise EngineError('engine_unavailable') from None
        finally:
            if sock is not None and not transferred:
                sock.close()

    def _json(self, method, path, deadline_ns, *, body=None, statuses=(200,), kind=dict):
        value = _loads(self._request(method, path, deadline_ns, body=body, statuses=statuses))
        _require(type(value) is kind, 'engine_protocol')
        return value

    def inspect(self, container_id, deadline_ns):
        _require(_id(container_id))
        value = self._json('GET', '/containers/' + container_id + '/json', deadline_ns)
        _require(value.get('Id') == container_id, 'engine_protocol')
        return value

    def inspect_image(self, image_id, deadline_ns):
        _require(_image(image_id))
        value = self._json('GET', '/images/' + image_id + '/json', deadline_ns)
        _require(value.get('Id') == image_id, 'engine_protocol')
        return value

    def info(self, deadline_ns):
        return self._json('GET', '/info', deadline_ns)

    def ping(self, deadline_ns):
        _require(self._request('GET', '/_ping', deadline_ns) == b'OK', 'engine_protocol')

    def create(self, nonce, image_id, api_container_id, deadline_ns):
        value = self._json('POST', '/containers/create', deadline_ns,
                           body=recipe(nonce, image_id, api_container_id), statuses=(201,))
        _require(_id(value.get('Id')), 'engine_protocol')
        return value['Id']

    def start(self, container_id, deadline_ns):
        _require(_id(container_id))
        self._request('POST', '/containers/' + container_id + '/start', deadline_ns, statuses=(204,))

    def attach(self, container_id, deadline_ns):
        _require(_id(container_id))
        return self._request('POST', '/containers/' + container_id +
                             '/attach?stream=1&stdin=1&stdout=1&stderr=1&logs=0', deadline_ns,
                             statuses=(101, 200), upgrade=True)

    def remove(self, container_id, deadline_ns):
        _require(_id(container_id))
        self._request('DELETE', '/containers/' + container_id + '?v=0&force=0', deadline_ns, statuses=(204,))

    def signal(self, container_id, signal, deadline_ns):
        _require(_id(container_id) and type(signal) is str and signal in ('SIGTERM', 'SIGKILL'))
        self._request('POST', '/containers/' + container_id + '/kill?signal=' + signal,
                      deadline_ns, statuses=(204,))

    def list_by_nonce(self, nonce, deadline_ns):
        _require(_id(nonce))
        filters = json.dumps({'label': [NONCE_LABEL + '=' + nonce]}, separators=(',', ':'))
        values = self._json('GET', '/containers/json?' + urlencode({'all': '1', 'filters': filters}),
                            deadline_ns, kind=list)
        _require(len(values) <= 8, 'engine_protocol')
        ids = []
        for value in values:
            _require(type(value) is dict and _id(value.get('Id')) and
                     type(value.get('Labels')) is dict and value['Labels'].get(NONCE_LABEL) == nonce,
                     'engine_protocol')
            ids.append(value['Id'])
        _require(len(set(ids)) == len(ids), 'engine_protocol')
        return tuple(sorted(ids))


class EngineTransport:
    """Translate the signed-off pure API protocol without adding operations."""
    def __init__(self, engine, image_id, api_container_id):
        _require(_image(image_id) and _id(api_container_id))
        self._engine, self._image, self._api = engine, image_id, api_container_id
        self._attachments = {}
        self._attach_used = set()

    def exchange(self, payload, *, deadline_ns, limit):
        _require(type(payload) is bytes and len(payload) <= 4096)
        _require(type(limit) is int and 0 < limit <= BODY_LIMIT)
        value = _loads(payload)
        _require(type(value) is dict and set(value) == {'op', 'image_digest', 'container_id', 'nonce', 'authorized_delete'})
        op, cid, nonce = value['op'], value['container_id'], value['nonce']
        _require(type(op) is str and op in ('create', 'start', 'attach', 'inspect', 'list_by_nonce', 'stop', 'delete'))
        _require(type(value['authorized_delete']) is bool and value['authorized_delete'] == (op == 'delete'))
        if op == 'create':
            _require(_id(nonce) and cid is None and value['image_digest'] == self._image)
        elif op == 'list_by_nonce':
            _require(_id(nonce) and cid is None and value['image_digest'] is None)
        else:
            _require(_id(cid) and nonce is None and value['image_digest'] is None)
        engine = self._engine
        if op == 'create':
            created = engine.create(nonce, self._image, self._api, deadline_ns)
            reply = {'container_id': created, 'created': True, 'nonce': nonce}
        elif op == 'list_by_nonce':
            reply = {'container_ids': list(engine.list_by_nonce(nonce, deadline_ns)), 'nonce': nonce}
        elif op == 'inspect':
            try:
                raw = engine.inspect(cid, deadline_ns)
            except EngineError as error:
                if str(error) != 'engine_not_found':
                    raise
                reply = {'container_id': cid, 'exists': False, 'running': False}
            else:
                state = raw.get('State')
                _require(type(state) is dict and type(state.get('Running')) is bool, 'engine_protocol')
                reply = {'container_id': cid, 'exists': True, 'running': state['Running']}
        elif op == 'start':
            engine.start(cid, deadline_ns)
            reply = {'container_id': cid, 'started': True}
        elif op == 'attach':
            _require(cid not in self._attach_used, 'engine_attach_used')
            self._attach_used.add(cid)
            self._attachments[cid] = engine.attach(cid, deadline_ns)
            reply = {'container_id': cid, 'attached': True}
        elif op == 'stop':
            # Signal is not proof of reclamation; callers independently inspect
            # and verify the exact cgroup before closing any journal record.
            engine.signal(cid, 'SIGTERM', deadline_ns)
            raw = engine.inspect(cid, deadline_ns)
            state = raw.get('State')
            _require(type(state) is dict and type(state.get('Running')) is bool, 'engine_protocol')
            reply = {'container_id': cid, 'stopped': not state['Running']}
        else:
            engine.remove(cid, deadline_ns)
            reply = {'container_id': cid, 'deleted': True}
        raw = json.dumps(reply, separators=(',', ':')).encode()
        _require(len(raw) <= limit, 'engine_protocol')
        return raw

    def take_attach(self, container_id):
        _require(_id(container_id) and container_id in self._attachments, 'engine_attach_used')
        return self._attachments.pop(container_id)
