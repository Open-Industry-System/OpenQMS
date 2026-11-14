import pytest
from openqms_agent_sdk._deadline import Deadline
from openqms_agent_sdk._transport import Transport
from openqms_agent_sdk.errors import ConfigError, ValidationError
from openqms_agent_sdk.models import ClientConfig, EncodedRequest, SUPPORTED_OPERATIONS
from test_deadline import no_network


@pytest.mark.parametrize('url', [
    'http://example.invalid', 'https://u:p@example.invalid',
    'https://example.invalid/prefix', 'https://example.invalid/?x=1',
    'https://example.invalid/#x', 'ftp://127.0.0.1',
    'https://example.invalid:bad', 'https://example.invalid?',
    'https://example.invalid#', 'https://example.invalid/\n',
])
def test_origin_is_restricted_without_network(url):
    with pytest.raises(ConfigError) as caught:
        Transport(ClientConfig(url))
    assert caught.value.kind == 'invalid_url'
    assert caught.value.__context__ is None


@pytest.mark.parametrize('tenant', ['', 'a\r\nb', 'a\x00b', 'a\x7fb', 'a\x85b', 'a\x9fb'])
def test_tenant_control_characters_rejected(tenant):
    with pytest.raises(ConfigError) as caught:
        Transport(ClientConfig('http://localhost', tenant_slug=tenant))
    assert caught.value.kind == 'invalid_tenant'


def test_unknown_operation_and_oversize_rejected_before_io():
    transport = Transport(ClientConfig('http://localhost'))
    try:
        for operation, body in [('unknown', b'{}'), ('claim', b'x' * (1024 * 1024 + 1))]:
            with pytest.raises(ValidationError):
                transport.exchange(operation, token=None, request=EncodedRequest(body, ()), deadline=Deadline(1, 'claim'))
    finally:
        transport.close()


@pytest.mark.parametrize('wire,expected,kind', [
    (b'HTTP/1.1 302 Found\r\nLocation: https://secret.invalid/\r\n\r\nsecret', 'HTTPError', 'redirect'),
    (b'HTTP/1.1 500 Bad\r\n\r\nsecret', 'HTTPError', 'http_status'),
    (b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 2\r\n\r\n{}', 'ProtocolError', 'invalid_response'),
    (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Encoding: gzip\r\nContent-Length: 2\r\n\r\n{}', 'ProtocolError', 'unsupported_encoding'),
    (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 65537\r\n\r\nsecret', 'ResponseTooLarge', 'response_too_large'),
    (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 3\r\n\r\n{}', 'ProtocolError', 'invalid_response'),
    (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\nContent-Length: 3\r\n\r\n{}', 'ProtocolError', 'invalid_response'),
])
def test_response_failures_are_bounded_and_sanitized(monkeypatch, wire, expected, kind):
    import socket
    from openqms_agent_sdk import errors
    from transport_fakes import FakeSocket
    fake = FakeSocket(wire, read_size=1)
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost', response_budget=65536))
    try:
        with pytest.raises(getattr(errors, expected)) as caught:
            transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
        assert caught.value.kind == kind
        assert caught.value.may_have_been_sent
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert 'secret' not in repr(caught.value)
        assert fake.refs == 0 and fake.released
        if expected in ('HTTPError', 'ResponseTooLarge'):
            assert fake.incoming  # headers rejected without reading the error body
    finally:
        transport.close()


@pytest.mark.parametrize('suffix', [b' ', b'\t'])
@pytest.mark.parametrize('stall_on_eof', [False, True])
def test_chunked_trailing_ows_uses_chunk_framing_not_eof(monkeypatch, suffix, stall_on_eof):
    import socket
    from transport_fakes import FakeSocket
    now = [0.0]
    wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
            b'Transfer-Encoding: chunked' + suffix + b'\r\nConnection: close\r\n\r\n'
            b'2\r\n{}\r\n0\r\n\r\n')
    class FramedSocket(FakeSocket):
        def advance(self, action):
            super().advance(action)
            if stall_on_eof and action == 'read' and not self.incoming:
                now[0] += 2
    fake = FramedSocket(wire, clock=now, read_size=1)
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost'))
    try:
        result = transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim', clock=lambda: now[0]))
        assert result.body == b'{}'
        assert now[0] == 0  # terminating chunk is sufficient: never wait for EOF
        assert fake.released and fake.refs == 0
    finally:
        transport.close()


@pytest.mark.parametrize('transfer_headers', [
    b'Transfer-Encoding: chunked \r\nTransfer-Encoding: chunked\r\n',
    b'Transfer-Encoding: chunked\t\r\nContent-Length: 2\r\n',
    b'Transfer-Encoding: gzip, chunked \r\n',
])
def test_chunked_ows_does_not_relax_ambiguous_transfer_headers(monkeypatch, transfer_headers):
    import socket
    from openqms_agent_sdk.errors import ProtocolError
    from transport_fakes import FakeSocket
    fake = FakeSocket(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n' + transfer_headers + b'Connection: close\r\n\r\n2\r\n{}\r\n0\r\n\r\n', read_size=1)
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost'))
    try:
        with pytest.raises(ProtocolError) as caught:
            transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
        assert caught.value.kind == 'invalid_response'
        assert fake.released and fake.refs == 0
    finally:
        transport.close()


@pytest.mark.parametrize('chunks', [b'2\r\n{}XX0\r\n\r\n', b'+2\r\n{}\r\n0\r\n\r\n', b'2\r\n{}\r\n0\r\nX-End: ok\r\n'])
def test_malformed_chunk_framing_rejected(monkeypatch, chunks):
    import socket
    from openqms_agent_sdk.errors import ProtocolError
    from transport_fakes import FakeSocket
    fake = FakeSocket(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n' + chunks, read_size=1)
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost'))
    try:
        with pytest.raises(ProtocolError):
            transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
        assert fake.released and fake.refs == 0
    finally:
        transport.close()


def test_tls_preserves_dns_name_and_remaining_handshake_budget(monkeypatch):
    import socket
    import ssl
    from transport_fakes import FakeSocket
    now = [0.0]
    fake = FakeSocket(clock=now, delays={'connect': .2})
    wraps = []
    class Context:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED
        def wrap_socket(self, raw, *, server_hostname, do_handshake_on_connect):
            wraps.append((server_hostname, do_handshake_on_connect))
            assert raw is fake
            now[0] += .1
            return fake
    def handshake():
        assert fake.timeouts[-1] == pytest.approx(.7)
        now[0] += .1
    fake.do_handshake = handshake
    monkeypatch.setattr(ssl, 'create_default_context', lambda: Context())
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', 443))])
    transport = Transport(ClientConfig('https://test.invalid'))
    try:
        response = transport.exchange('claim', token='ignored', request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim', clock=lambda: now[0]))
        assert response.body == b'{}'
        assert wraps == [('test.invalid', False)]
        assert b'Authorization:' not in fake.sent
    finally:
        transport.close()


@pytest.mark.parametrize('phase', ['send', 'status', 'headers', 'body', 'chunk_size', 'extension', 'crlf', 'trailer', 'continue'])
def test_every_partial_io_uses_same_deadline(monkeypatch, phase):
    import socket
    from openqms_agent_sdk.errors import RequestTimeout
    from transport_fakes import FakeSocket
    header = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
    chunk_header = header + b'Transfer-Encoding: chunked\r\n\r\n'
    prefixes = {
        'send': b'', 'status': b'', 'headers': b'HTTP/1.1 200 OK\r\n',
        'body': header + b'Content-Length: 10\r\n\r\n',
        'chunk_size': chunk_header, 'extension': chunk_header + b'2;',
        'crlf': chunk_header + b'2\r\n{}',
        'trailer': chunk_header + b'2\r\n{}\r\n0\r\n',
        'continue': b'HTTP/1.1 100 Continue\r\n',
    }
    suffixes = {
        'send': header + b'Content-Length: 2\r\n\r\n{}',
        'status': header + b'Content-Length: 2\r\n\r\n{}',
        'headers': b'Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}',
        'body': b'0123456789', 'chunk_size': b'0002\r\n{}\r\n0\r\n\r\n',
        'extension': b'abc=def\r\n{}\r\n0\r\n\r\n',
        'crlf': b'\r\n0\r\n\r\n', 'trailer': b'X-End: ok\r\n\r\n',
        'continue': b'X-A: b\r\n\r\n' + header + b'Content-Length: 2\r\n\r\n{}',
    }
    wire = prefixes[phase] + suffixes[phase]
    now = [0.0]
    class SlowSocket(FakeSocket):
        def advance(self, action):
            super().advance(action)
            if action == 'send' and phase == 'send':
                now[0] += .4
            elif action == 'read' and phase != 'send' and len(wire) - len(self.incoming) >= len(prefixes[phase]):
                now[0] += .4
    fake = SlowSocket(wire, clock=now, read_size=1, send_size=7)
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost'))
    try:
        with pytest.raises(RequestTimeout) as caught:
            transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim', clock=lambda: now[0]))
        assert caught.value.kind == 'deadline' and caught.value.may_have_been_sent
        assert now[0] == pytest.approx(1.2)
        assert fake.timeouts[-1] == pytest.approx(.2)
        assert fake.released and fake.refs == 0
        assert caught.value.__context__ is None
    finally:
        transport.close()


def test_zero_send_is_connection_closed_with_safe_metadata(monkeypatch):
    import socket
    from openqms_agent_sdk.errors import TransportError
    from transport_fakes import FakeSocket
    fake = FakeSocket(send_size=0)
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost'))
    try:
        with pytest.raises(TransportError) as caught:
            transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
        assert caught.value.kind == 'connection_closed'
        assert caught.value.may_have_been_sent
        assert caught.value.__context__ is None
        assert fake.released
    finally:
        transport.close()


@pytest.mark.parametrize('framing', ['length', 'close', 'chunked'])
@pytest.mark.parametrize('size', [65536, 65537])
def test_response_budget_exact_n_and_n_plus_one(monkeypatch, framing, size):
    import socket
    from openqms_agent_sdk.errors import ResponseTooLarge
    from transport_fakes import FakeSocket
    body = b'x' * size
    headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
    if framing == 'length':
        wire = headers + f'Content-Length: {size}\r\n\r\n'.encode() + body
    elif framing == 'chunked':
        wire = headers + b'Transfer-Encoding: chunked\r\n\r\n' + f'{size:x}\r\n'.encode() + body + b'\r\n0\r\n\r\n'
    else:
        wire = headers + b'Connection: close\r\n\r\n' + body
    fake = FakeSocket(wire)
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost', response_budget=65536))
    try:
        if size == 65536:
            result = transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
            assert len(result.body) == size
        else:
            with pytest.raises(ResponseTooLarge):
                transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
        assert fake.released and fake.refs == 0
    finally:
        transport.close()


@pytest.mark.parametrize('phase', ['connect', 'tls', 'send', 'read'])
def test_io_exception_metadata_has_no_original_context(monkeypatch, phase):
    import socket
    import ssl
    from openqms_agent_sdk.errors import TransportError
    from transport_fakes import FakeSocket
    fake = FakeSocket(read_size=1)
    def fail(*a, **kw):
        raise (ssl.SSLError('secret host token body') if phase == 'tls' else OSError('secret host token body'))
    if phase in ('connect', 'send'):
        setattr(fake, phase, fail)
    elif phase == 'read':
        fake.advance = lambda action: fail() if action == 'read' else None
    else:
        class Context:
            wrap_socket = fail
        monkeypatch.setattr(ssl, 'create_default_context', lambda: Context())
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('https://127.0.0.1' if phase == 'tls' else 'http://127.0.0.1'))
    try:
        with pytest.raises(TransportError) as caught:
            transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
        assert caught.value.kind == {'connect': 'connection', 'tls': 'tls', 'send': 'connection_closed', 'read': 'connection_closed'}[phase]
        assert caught.value.may_have_been_sent == (phase in ('send', 'read'))
        assert caught.value.__context__ is None and caught.value.__cause__ is None
        assert 'secret' not in repr(caught.value)
        assert fake.released and fake.refs == 0
    finally:
        transport.close()


@pytest.mark.parametrize('second_delay,expires', [(.4, False), (.7, True)])
def test_multiple_connect_candidates_share_dns_and_connect_budget(monkeypatch, second_delay, expires):
    import socket
    import ssl
    from openqms_agent_sdk.errors import RequestTimeout
    from transport_fakes import FakeSocket
    now = [0.0]
    first = FakeSocket(clock=now)
    second = FakeSocket(clock=now, delays={'connect': second_delay})
    def fail_connect(address):
        now[0] += .4
        raise OSError('not retained')
    first.connect = fail_connect
    second.do_handshake = lambda: None
    class Context:
        def wrap_socket(self, raw, **kwargs):
            return raw
    monkeypatch.setattr(ssl, 'create_default_context', lambda: Context())
    candidates = iter([first, second])
    monkeypatch.setattr(socket, 'socket', lambda *a: next(candidates))
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', 443)), (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.2', 443))])
    transport = Transport(ClientConfig('https://test.invalid'))
    try:
        if expires:
            with pytest.raises(RequestTimeout) as caught:
                transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim', clock=lambda: now[0]))
            assert not caught.value.may_have_been_sent and not second.sent
        else:
            result = transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim', clock=lambda: now[0]))
            assert result.body == b'{}'
        assert second.timeouts[0] == pytest.approx(.6)
        assert first.released and second.released
    finally:
        transport.close()


@pytest.mark.parametrize('operation', list(SUPPORTED_OPERATIONS))
def test_only_fixed_operation_routes_and_runtime_bearer(monkeypatch, operation):
    import socket
    from openqms_agent_sdk.models import SUPPORTED_OPERATIONS
    from transport_fakes import FakeSocket
    fake = FakeSocket()
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost'))
    try:
        transport.exchange(operation, token='synthetic', request=EncodedRequest(None, (('q', '/?&\r\n'),)), deadline=Deadline(1, operation))
        method, path = SUPPORTED_OPERATIONS[operation]
        assert fake.sent.startswith(f'{method} {path}?q=%2F%3F%26%0D%0A HTTP/1.1\r\n'.encode())
        assert (b'Authorization: Bearer synthetic\r\n' in fake.sent) == (operation != 'claim')
    finally:
        transport.close()


@pytest.mark.parametrize('wire', [b'not-http\r\n', b'HTTP/1.1 200 OK\r\n' + b'X-Bad: ' + b'x' * 65536 + b'\r\n'])
def test_header_failure_releases_owner_and_raw_io_ref(monkeypatch, wire):
    import socket
    from openqms_agent_sdk.errors import ProtocolError
    from transport_fakes import FakeSocket
    fake = FakeSocket(wire)
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost'))
    try:
        with pytest.raises(ProtocolError) as caught:
            transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
        assert caught.value.may_have_been_sent and caught.value.__context__ is None
        assert fake.released and fake.refs == 0
    finally:
        transport.close()


def test_exact_one_mib_request_is_allowed(monkeypatch):
    import socket
    from transport_fakes import FakeSocket
    fake = FakeSocket(send_size=10000)
    monkeypatch.setattr(socket, 'socket', lambda *a: fake)
    transport = Transport(ClientConfig('http://localhost'))
    body = b'x' * (1024 * 1024)
    try:
        result = transport.exchange('claim', token=None, request=EncodedRequest(body, ()), deadline=Deadline(1, 'claim'))
        assert result.body == b'{}'
        assert fake.sent.endswith(body) and fake.released
    finally:
        transport.close()


def test_real_http_parser_close_body_and_fixed_headers(monkeypatch):
    import socket
    from transport_fakes import FakeSocket
    fake = FakeSocket(send_size=7)
    monkeypatch.setattr(socket, 'socket', lambda *a, **kw: fake)
    transport = Transport(ClientConfig('http://localhost:12345', tenant_slug='trusted'))
    try:
        response = transport.exchange('capabilities', token='secret', request=EncodedRequest(None, ()), deadline=Deadline(1, 'capabilities'))
        assert response.status == 200 and response.body == b'{}'
        assert response.may_have_been_sent
        assert b'GET /api/agent/runtime/capabilities HTTP/1.1\r\n' in fake.sent
        assert b'Authorization: Bearer secret\r\n' in fake.sent
        assert b'X-Tenant-ID: trusted\r\n' in fake.sent
        assert b'Connection: close\r\n' in fake.sent
        assert b'Forwarded' not in fake.sent
        assert fake.refs == 0 and fake.released
    finally:
        transport.close()
