"""Synchronous stdlib transport. No ambient proxy, cookies or credential stores."""
import http.client
import io
import ipaddress
import ssl
import queue
import socket
import threading

from urllib.parse import urlsplit, urlencode

from .errors import (ClientClosed, ConfigError, HTTPError, ProtocolError,
                     RequestTimeout, ResponseTooLarge, SDKError, TransportError,
                     ValidationError)
from .models import REQUEST_BUDGET, SUPPORTED_OPERATIONS, WireResponse


class DeadlineRaw(io.RawIOBase):
    def __init__(self, raw, real, deadline):
        super().__init__()
        self._raw, self._real, self._deadline = raw, real, deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        self._real.settimeout(self._deadline.remaining())
        count = self._raw.readinto(buffer)
        self._deadline.check()
        return count

    def close(self):
        try:
            self._raw.close()
        finally:
            super().close()


class DeadlineSocket:
    def __init__(self, real, deadline, state):
        self._real, self._deadline, self._state = real, deadline, state

    def makefile(self, mode):
        # Acquire the real socket's IO reference BEFORE connection.close can
        # run on will_close. A closed facade must not disable a live reader.
        raw = self._real.makefile(mode, buffering=0)
        return io.BufferedReader(DeadlineRaw(raw, self._real, self._deadline))

    def sendall(self, data):
        view = memoryview(data)
        while view:
            self._real.settimeout(self._deadline.remaining())
            self._state['sent'] = True
            count = self._real.send(view)
            self._deadline.check()
            if count <= 0:
                raise TransportError(self._deadline.operation, kind='connection_closed')
            view = view[count:]

    def close(self):
        # socket.close defers final release while makefile owns its IO ref.
        # No shutdown, detach, os.close, or private IO-ref manipulation.
        self._real.close()


class _Response(http.client.HTTPResponse):
    """Keep stdlib HTTP parsing, but reject permissive chunk framing/EOF."""
    def begin(self):
        if self.headers is not None:
            return
        super().begin()
        transfers = self.headers.get_all('Transfer-Encoding', [])
        # Match the validator's normalization before any body read. Only an
        # unambiguous chunked response is eligible; bodyless statuses retain
        # stdlib's zero length, and duplicate TE / TE+CL remain rejected later.
        if (self.length is None and len(transfers) == 1
                and transfers[0].strip().lower() == 'chunked'
                and not self.headers.get_all('Content-Length', [])):
            self.chunked = True
            self.chunk_left = None
            self.length = None

    def _read_next_chunk_size(self):
        line = self.fp.readline(65537)
        if len(line) > 65536 or not line.endswith(b'\r\n'):
            raise http.client.HTTPException('invalid chunk line')
        size, _, extension = line[:-2].partition(b';')
        if not size or any(c not in b'0123456789abcdefABCDEF' for c in size):
            raise http.client.HTTPException('invalid chunk size')
        if any(c < 32 or c > 126 for c in extension):
            raise http.client.HTTPException('invalid chunk extension')
        return int(size, 16)

    def _get_chunk_left(self):
        left = self.chunk_left
        if not left:
            if left is not None and self._safe_read(2) != b'\r\n':
                raise http.client.HTTPException('invalid chunk separator')
            left = self._read_next_chunk_size()
            if left == 0:
                self._read_and_discard_trailer()
                self._close_conn()
                left = None
            self.chunk_left = left
        return left

    def _read_and_discard_trailer(self):
        total = 0
        for _ in range(101):
            line = self.fp.readline(65537)
            total += len(line)
            if total > 65536 or not line.endswith(b'\r\n'):
                raise http.client.HTTPException('invalid trailer')
            if line == b'\r\n':
                return
            if b':' not in line or any(c < 32 and c != 9 for c in line[:-2]):
                raise http.client.HTTPException('invalid trailer')
        raise http.client.HTTPException('too many trailers')


class _Connection(http.client.HTTPConnection):
    response_class = _Response

    def __init__(self, transport, deadline, state):
        super().__init__(transport._host, transport._port)
        self._transport, self._deadline, self._state = transport, deadline, state

    def connect(self):
        owner = self._transport
        candidates = owner._resolver.resolve(owner._host, owner._port, self._deadline)
        for family, socktype, proto, _, address in candidates:
            real = None
            connected = False
            try:
                real = socket.socket(family, socktype, proto)
                real.settimeout(self._deadline.remaining())
                real.connect(address)
                self._deadline.check()
                connected = True
            except OSError:
                pass
            finally:
                if real is not None and not connected:
                    real.close()
            self._deadline.check()
            if connected:
                try:
                    if owner._tls:
                        context = ssl.create_default_context()
                        self._deadline.check()
                        real = context.wrap_socket(real, server_hostname=owner._host, do_handshake_on_connect=False)
                        real.settimeout(self._deadline.remaining())
                        real.do_handshake()
                        self._deadline.check()
                    self.sock = DeadlineSocket(real, self._deadline, self._state)
                finally:
                    if self.sock is None:
                        real.close()
                return
        raise TransportError(self._deadline.operation, kind='connection')


class Resolver:
    """At most one daemon and outstanding lookup per instance.

    OS name resolution cannot be forcibly cancelled. Only the waiting caller is
    bounded; a late result is discarded, and never opens a socket.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = queue.Queue(maxsize=1)
        self._thread = None
        self._active = None
        self._closed = False

    def resolve(self, host, port, deadline):
        deadline.check()
        if host == 'localhost':
            host = '127.0.0.1'
        address = None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            pass
        with self._lock:
            if self._closed:
                raise ClientClosed(deadline.operation, kind='client_closed')
            if address is not None:
                family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
                sockaddr = (str(address), port, 0, 0) if address.version == 6 else (str(address), port)
                return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', sockaddr)]
            if self._active is not None:
                raise TransportError(deadline.operation, kind='dns_busy')
            result = queue.Queue(maxsize=1)
            cancelled = threading.Event()
            job = (host, port, result, cancelled)
            self._active = job
            if self._thread is None:
                self._thread = threading.Thread(target=self._work, name='openqms-dns', daemon=True)
                self._thread.start()
            self._jobs.put_nowait(job)
        reply = None
        try:
            try:
                reply = result.get(timeout=deadline.remaining())
            except queue.Empty:
                pass
            deadline.check()
            if reply is None:
                raise RequestTimeout(deadline.operation, kind='deadline')
            if not reply[0]:
                raise TransportError(deadline.operation, kind='dns')
            return reply[1]
        finally:
            cancelled.set()

    def _work(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return
            host, port, result, cancelled = job
            reply = (False, None)
            try:
                values = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
                reply = (True, values)
                del values
            except Exception:
                pass
            with self._lock:
                if not cancelled.is_set() and not self._closed:
                    result.put_nowait(reply)
                self._active = None
                closed = self._closed
            del job, host, port, result, cancelled, reply
            if closed:
                return

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._active is not None:
                self._active[3].set()
            elif self._thread is not None:
                self._jobs.put_nowait(None)


class Transport:
    def __init__(self, config):
        self._config = config
        self._resolver = Resolver()
        self._closed = False
        parsed = None
        valid = False
        try:
            url = config.base_url
            if type(url) is str and not any(ord(c) <= 32 or ord(c) == 127 for c in url) and '?' not in url and '#' not in url and '\\' not in url:
                parsed = urlsplit(url)
                host, port = parsed.hostname, parsed.port
                valid = (parsed.scheme in ('http', 'https') and bool(host)
                         and parsed.username is None and parsed.password is None
                         and parsed.path in ('', '/') and (port is None or 1 <= port <= 65535))
                if valid and parsed.scheme == 'http' and host != 'localhost':
                    valid = ipaddress.ip_address(host).is_loopback
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise ConfigError('config', kind='invalid_url')
        tenant = config.tenant_slug
        if tenant is not None and (type(tenant) is not str or not tenant.strip()
                                   or any(ord(c) < 32 or 127 <= ord(c) < 160 or ord(c) > 255 for c in tenant)):
            raise ConfigError('config', kind='invalid_tenant')
        self._host = parsed.hostname
        self._tls = parsed.scheme == 'https'
        self._port = parsed.port or (443 if self._tls else 80)

    def close(self):
        self._closed = True
        self._resolver.close()

    def _prepare(self, operation, token, request):
        if type(operation) is not str or operation not in SUPPORTED_OPERATIONS:
            raise ValidationError(operation, kind='invalid_request')
        if type(request.body) is not bytes and request.body is not None:
            raise ValidationError(operation, kind='invalid_request')
        if request.body is not None and len(request.body) > REQUEST_BUDGET:
            raise ValidationError(operation, kind='request_too_large')
        if type(request.query) is not tuple or any(type(pair) is not tuple or len(pair) != 2 or any(type(v) is not str for v in pair) for pair in request.query):
            raise ValidationError(operation, kind='invalid_request')
        method, path = SUPPORTED_OPERATIONS[operation]
        query = urlencode(request.query)
        if len(query) > REQUEST_BUDGET:
            raise ValidationError(operation, kind='request_too_large')
        if query:
            path += '?' + query
        headers = {'Connection': 'close', 'Accept': 'application/json'}
        if request.body is not None:
            headers['Content-Type'] = 'application/json'
        if self._config.tenant_slug is not None:
            headers['X-Tenant-ID'] = self._config.tenant_slug
        if operation != 'claim':
            if type(token) is not str or not token or any(ord(c) <= 32 or ord(c) >= 127 for c in token):
                raise ValidationError(operation, kind='invalid_request')
            headers['Authorization'] = 'Bearer ' + token
        return method, path, headers

    def exchange(self, operation, *, token, request, deadline):
        deadline.check()
        if self._closed:
            raise ClientClosed(operation, kind='client_closed')
        method, path, headers = self._prepare(operation, token, request)
        return self._exchange(operation, method, path, headers, request.body, deadline)

    def _validate_response(self, response, operation):
        def values(name):
            return response.headers.get_all(name, [])
        content_types = values('Content-Type')
        if len(content_types) != 1 or content_types[0].split(';', 1)[0].strip().lower() != 'application/json':
            raise ProtocolError(operation, kind='invalid_response', status=response.status)
        encodings = values('Content-Encoding')
        if encodings and (len(encodings) != 1 or encodings[0].strip().lower() != 'identity'):
            raise ProtocolError(operation, kind='unsupported_encoding', status=response.status)
        lengths, transfers = values('Content-Length'), values('Transfer-Encoding')
        if transfers and (len(transfers) != 1 or transfers[0].strip().lower() != 'chunked' or lengths):
            raise ProtocolError(operation, kind='invalid_response', status=response.status)
        if not lengths:
            return None
        if len(lengths) != 1 or not lengths[0] or any(c not in '0123456789' for c in lengths[0]):
            raise ProtocolError(operation, kind='invalid_response', status=response.status)
        number = lengths[0].lstrip('0') or '0'
        if len(number) > 20 or int(number) > self._config.response_budget:
            raise ResponseTooLarge(operation, kind='response_too_large', status=response.status)
        return int(number)

    def _exchange(self, operation, method, path, headers, body, deadline):
        state = {'sent': False}
        connection = _Connection(self, deadline, state)
        response = None
        failure = None
        result = None
        try:
            connection.request(method, path, body=body, headers=headers)
            deadline.check()
            response = connection.getresponse()
            deadline.check()
            if not 200 <= response.status < 300:
                kind = 'redirect' if 300 <= response.status < 400 else 'http_status'
                raise HTTPError(operation, kind=kind, status=response.status)
            expected = self._validate_response(response, operation)
            pieces, total = [], 0
            while True:
                deadline.check()
                piece = response.read(min(65536, self._config.response_budget + 1 - total))
                deadline.check()
                total += len(piece)
                if total > self._config.response_budget:
                    raise ResponseTooLarge(operation, kind='response_too_large', status=response.status)
                if not piece:
                    break
                pieces.append(piece)
            if expected is not None and total != expected:
                raise ProtocolError(operation, kind='invalid_response', status=response.status)
            deadline.check()
            result = WireResponse(response.status, b''.join(pieces), state['sent'])
            deadline.check()
        except SDKError as exc:
            failure = (type(exc), exc.kind, exc.status)
        except TimeoutError:
            failure = (RequestTimeout, 'deadline', None)
        except ssl.SSLError:
            failure = (TransportError, 'tls', None)
        except OSError:
            failure = (TransportError, 'connection_closed' if state['sent'] else 'connection', None)
        except (http.client.HTTPException, ValueError):
            failure = (ProtocolError, 'invalid_response', None)
        finally:
            try:
                if response is not None:
                    response.close()
            finally:
                connection.close()
        if failure is not None:
            cls, kind, status = failure
            raise cls(operation, kind=kind, status=status, may_have_been_sent=state['sent']) from None
        return result
