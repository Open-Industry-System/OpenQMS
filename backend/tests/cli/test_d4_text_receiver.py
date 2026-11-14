"""Standalone receiver tests runnable without backend conftest or dependencies."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    assert path.is_file(), 'fixed receiver implementation absent'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fx = load(ROOT / 'tests/e2e/d4_text_wire_fixture.py', 'd4_wire_fixture')


@pytest.fixture
def receiver():
    return load(ROOT / 'examples/readonly_d4_text_receiver.py', 'd4_receiver_test')


def run(receiver, origin):
    cfg = receiver.Config.from_mapping(fx.config(origin))
    return receiver.safe_receive(receiver.FixedWire(cfg), cfg)


def test_six_operations_and_actual_ack(receiver):
    with fx.server(fx.responses()) as (origin, requests):
        result = run(receiver, origin)
    assert result == dict(status='completed', receipt_id=fx.RECEIPT, received_fields=1)
    assert [r[0].split()[1].decode() for r in requests] == [
        '/api/agent/runtime/'+p for p in ('claim', 'capabilities', 'messages/claim', 'capa/d4/root-cause-text', 'messages/ack', 'finish')]
    assert json.loads(requests[4][2]) == dict(batch_id=fx.BATCH, through_sequence=1)
    assert b'Authorization' not in requests[0][1]
    assert all(r[1][b'Authorization'] == ('Bearer '+fx.TOKEN).encode() for r in requests[1:])
    assert fx.TEXT not in repr(result)


@pytest.mark.parametrize('field,value', [('run_id',fx.TASK), ('task_id',fx.RUN), ('report_id',fx.RUN),
    ('recipient_installation_id',fx.RUN), ('data_class','internal'), ('projection','raw'),
    ('model_delivery_allowed',0), ('source_authorization','stale'), ('source_proof','unknown'),
    ('delivery_scope','model'), ('field','d5'), ('source_version','A'*64), ('generated_at','2026-01-01'),
    ('text',12), ('projection_id','capa.d4.summary.masked.v1')])
def test_bad_body_never_acknowledged(receiver, field, value):
    replies = fx.responses()
    replies[3][field] = value
    with fx.server(replies) as (origin, requests):
        assert run(receiver, origin)['status'] == 'unconfirmed'
    assert len(requests) == 4


def test_nonliteral_message_stops_before_body(receiver):
    replies = fx.responses()
    replies[2]['messages'][0]['content'] = fx.TEXT
    with fx.server(replies) as (origin, requests):
        assert run(receiver, origin)['status'] == 'input_unconfirmed'
    assert len(requests) == 3


@pytest.mark.parametrize('body', [b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff', b'{', b'[]'])
def test_malformed_body_is_not_retained(receiver, body):
    replies = fx.responses()
    replies[3] = fx.reply(body)
    with fx.server(replies) as (origin, requests):
        result = run(receiver, origin)
    assert result == dict(status='unconfirmed', received_fields=0)
    assert len(requests) == 4


@pytest.mark.parametrize('response', [b'', fx.reply(b'{'), fx.reply(b'x'*(256*1024+1)), fx.reply(dict(run_id=fx.TASK))], ids=['disconnect','bad-json','oversize','wrong-binding'])
def test_finish_without_confirmation_is_unknown_once(receiver, response):
    replies = fx.responses()
    replies[5] = response
    with fx.server(replies) as (origin, requests):
        assert run(receiver, origin)['status'] == 'unknown'
    assert len(requests) == 6


@pytest.mark.parametrize('origin', ['http://localhost:80','http://127.0.0.2:80','https://example.com',
    'http://127.0.0.1/','http://x@127.0.0.1','http://127.0.0.1?','http://127.0.0.1#','http://127.0.0.1\\evil'])
def test_origin_is_exact_numeric(receiver, origin):
    with pytest.raises(receiver.SafeFailure):
        receiver.Config.from_mapping(fx.config(origin))


def test_fixed_executable_exists():
    assert (ROOT / 'examples/readonly_d4_text_receiver.py').is_file()


@pytest.mark.parametrize('headers,body', [
    (b'Transfer-Encoding: chunked \t\r\n', b'2\r\n{}\r\n0\r\n\r\n'),
    (b'Transfer-Encoding: chunked\r\nContent-Length: 2\r\n', b'{}'),
    (b'Content-Length: 2\r\nContent-Length: 2\r\n', b'{}'),
    (b'Content-Length: 2,2\r\n', b'{}'),
    (b'Transfer-Encoding: chunked\r\n', b'+2\r\n{}\r\n0\r\n\r\n'),
    (b'Transfer-Encoding: chunked\r\n', b'2\r\n{}xx0\r\n\r\n'),
    (b'Transfer-Encoding: chunked\r\n', b'0\r\nX: '+b'a'*33000+b'\r\n\r\n'),
    (b'Content-Length: 2\r\n'+b'X: a\r\n'*101, b'{}'),
    (b'Content-Length: 9\r\n', b'{}'),
], ids=['te-ows', 'te-cl', 'duplicate-cl', 'list-cl', 'chunk-sign', 'chunk-separator', 'trailer-limit', 'header-count', 'truncated-cl'])
def test_raw_framing(receiver, headers, body):
    with fx.server([fx.reply(body, headers)]) as (origin, requests):
        cfg = receiver.Config.from_mapping(fx.config(origin))
        with pytest.raises(receiver.SafeFailure) as caught:
            receiver.FixedWire(cfg).claim(cfg)
    assert caught.value.__context__ is None
    assert len(requests) == 1


def test_chunked_with_ows_real_success(receiver):
    replies = fx.responses()
    raw = json.dumps(replies[3]).encode()
    replies[3] = fx.reply(hex(len(raw))[2:].encode()+b'\r\n'+raw+b'\r\n0\r\n\r\n', b'Transfer-Encoding: chunked \t\r\n')
    with fx.server(replies) as (origin, requests):
        assert run(receiver, origin)['status'] == 'completed'
    assert len(requests) == 6


def test_slow_drip_cannot_reset_deadline(receiver, monkeypatch):
    import time
    monkeypatch.setattr(receiver, 'OPERATION_SECONDS', .12)
    def drip(conn):
        for byte in fx.reply(fx.responses()[0]):
            conn.send(bytes([byte]))
            time.sleep(.015)
    started = time.monotonic()
    with fx.server([drip]) as (origin, requests):
        assert run(receiver, origin)['status'] == 'unconfirmed'
    assert time.monotonic()-started < .8
    assert len(requests) == 1


def test_late_json_decode_and_schema_cannot_succeed(receiver, monkeypatch):
    original = receiver.parse_json
    now = [0.0]
    monkeypatch.setattr(receiver.time, 'monotonic', lambda: now[0])
    def late(raw):
        value = original(raw)
        now[0] = 11.0
        return value
    monkeypatch.setattr(receiver, 'parse_json', late)
    with fx.server(fx.responses()) as (origin, requests):
        assert run(receiver, origin)['status'] == 'unconfirmed'
    assert len(requests) == 1


def test_partial_sends_share_one_deadline(receiver, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(receiver.time, 'monotonic', lambda: now[0])
    timeouts, pieces = [], []
    class Partial:
        def settimeout(self, value):
            timeouts.append(value)
        def send(self, data):
            pieces.append(bytes(data[:2]))
            now[0] += 4
            return min(2, len(data))
    state = {'sent': False}
    with pytest.raises(receiver.SafeFailure):
        receiver.send_all(Partial(), b'abcdefghi', receiver.Deadline(), state)
    assert state['sent'] is True and timeouts == [10, 6, 2]
    assert b''.join(pieces) == b'abcdef'


def test_finish_late_decode_is_unknown_and_not_retried(receiver, monkeypatch):
    original = receiver.parse_json
    now = [0.0]
    monkeypatch.setattr(receiver.time, 'monotonic', lambda: now[0])
    def late(raw):
        value = original(raw)
        if 'run_status' in value:
            now[0] = 11.0
        return value
    monkeypatch.setattr(receiver, 'parse_json', late)
    with fx.server(fx.responses()) as (origin, requests):
        assert run(receiver, origin)['status'] == 'unknown'
    assert len(requests) == 6


def test_unknown_nonsecurity_field_discarded_and_repr_hidden(receiver):
    replies = fx.responses()
    replies[3]['future_metadata'] = {'opaque': fx.SECRET}
    with fx.server(replies) as (origin, requests):
        cfg = receiver.Config.from_mapping(fx.config(origin))
        wire = receiver.FixedWire(cfg)
        claim = wire.claim(cfg)
        wire.require_body_capability(claim)
        batch = wire.claim_start(claim)
        delivery = wire.read_body(claim)
        assert not hasattr(delivery, 'future_metadata')
        assert all(s not in repr((cfg, claim, batch, delivery)) for s in (fx.TEXT, fx.SECRET, fx.TOKEN, fx.START))
        wire.ack_start(claim, batch)
        wire.finish_once(claim)


@pytest.mark.parametrize('status,expected', [(302,'unknown'), (403,'rejected'), (500,'unknown'), (429,'unknown')])
def test_finish_explicit_rejection_is_not_terminal_guess(receiver, status, expected):
    replies = fx.responses()
    replies[5] = ('HTTP/1.1 '+str(status)+' Rejected\r\nContent-Length: 0\r\n\r\n').encode()
    with fx.server(replies) as (origin, requests):
        assert run(receiver, origin)['status'] == expected
    assert len(requests) == 6


def test_final_return_after_close_still_obeys_deadline(receiver, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(receiver.time, 'monotonic', lambda: now[0])
    response = fx.reply(fx.responses()[-1])
    class Socket:
        def settimeout(self, value): pass
        def connect(self, address): pass
        def send(self, data): return len(data)
        def recv(self, size): return response
        def close(self): now[0] = 11
    monkeypatch.setattr(receiver.socket, 'socket', lambda *a: Socket())
    cfg = receiver.Config.from_mapping(fx.config('http://127.0.0.1:1'))
    wire = receiver.FixedWire(cfg)
    with pytest.raises(receiver.SafeFailure) as caught:
        wire.finish_once(receiver.ClaimView(fx.RUN, fx.TASK, fx.TOKEN))
    assert caught.value.status == 'unknown'


def test_real_tls_raw_io_and_certificate_validation(receiver, tmp_path, monkeypatch):
    import ssl
    import subprocess
    key, cert = tmp_path / 'key.pem', tmp_path / 'cert.pem'
    subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=127.0.0.1',
                    '-addext', 'subjectAltName=IP:127.0.0.1'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    key.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    original = ssl.create_default_context
    def trusted_local_context():
        client = original(cafile=str(cert))
        assert client.verify_mode == ssl.CERT_REQUIRED and client.check_hostname
        return client
    monkeypatch.setattr(receiver.ssl, 'create_default_context', trusted_local_context)
    with fx.server(fx.responses(), tls_context=context) as (origin, requests):
        assert run(receiver, origin)['status'] == 'completed'
    assert len(requests) == 6


def test_tls_partial_send_and_io_never_uses_makefile(receiver, monkeypatch):
    now, timeouts = [0.0], []
    response = fx.reply(fx.responses()[0])
    class TLS:
        def settimeout(self, value): timeouts.append(value)
        def connect(self, address): now[0] += 1
        def do_handshake(self): now[0] += 1
        def send(self, data):
            now[0] += .1
            return min(100, len(data))
        def recv(self, size):
            now[0] += 1
            return response
        def makefile(self, *a): pytest.fail('TLS IO reference must not be detached')
        def close(self): pass
    sock = TLS()
    class Context:
        def wrap_socket(self, value, *, server_hostname, do_handshake_on_connect):
            assert value is sock and server_hostname == '127.0.0.1' and do_handshake_on_connect is False
            return sock
    monkeypatch.setattr(receiver.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(receiver.socket, 'socket', lambda *a: sock)
    monkeypatch.setattr(receiver.ssl, 'create_default_context', lambda: Context())
    cfg = receiver.Config.from_mapping(fx.config('https://127.0.0.1:1'))
    claim = receiver.FixedWire(cfg).claim(cfg)
    assert claim.run_id == fx.RUN
    assert all(a > b for a, b in zip(timeouts, timeouts[1:]))


def test_request_budget_counts_encoded_bytes_and_headers(receiver, monkeypatch):
    cfg = receiver.Config.from_mapping(fx.config('http://127.0.0.1:1'))
    def forbidden(*args): pytest.fail('oversize request opened socket')
    monkeypatch.setattr(receiver.socket, 'socket', forbidden)
    claim = receiver.ClaimView(fx.RUN, fx.TASK, 't' * receiver.REQUEST_LIMIT)
    with pytest.raises(receiver.SafeFailure):
        receiver.FixedWire(cfg).require_body_capability(claim)


def test_config_hides_invalid_values_without_exception_chain(receiver):
    bad = fx.config('http://127.0.0.1:1')
    bad['installation_id'] = fx.SECRET
    with pytest.raises(receiver.SafeFailure) as caught:
        receiver.Config.from_mapping(bad)
    assert fx.SECRET not in str(caught.value)
    assert caught.value.__context__ is None and caught.value.__cause__ is None


HEADER = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
CHUNK = HEADER + b'Transfer-Encoding: chunked\r\n\r\n'


@pytest.mark.parametrize('prefix,drip', [
    (b'', b'HTTP/1.1 200 OK\r\n'),
    (b'HTTP/1.1 200 OK\r\n', b'Content-Type: application/json\r\n'),
    (HEADER+b'Content-Length: 10\r\n\r\n', b'0123456789'),
    (CHUNK, b'00000002;ok=yes\r\n'),
    (CHUNK+b'2;', b'name=value\r\n'),
    (CHUNK+b'2\r\n{}', b'\r\n0\r\n\r\n'),
    (CHUNK+b'2\r\n{}\r\n0\r\n', b'X-End: yes\r\n\r\n'),
    (b'HTTP/1.1 100 Continue\r\n', b'X-Wait: yes\r\n\r\n'),
], ids=['status','headers','body','chunk-size','extension','crlf','trailer','interim'])
def test_sdk_slow_drip_counterexamples(receiver, monkeypatch, prefix, drip):
    import time
    monkeypatch.setattr(receiver, 'OPERATION_SECONDS', .12)
    def serve(conn):
        conn.sendall(prefix)
        for byte in drip:
            time.sleep(.025)
            conn.sendall(bytes([byte]))
    start = time.monotonic()
    with fx.server([serve]) as (origin, requests):
        assert run(receiver, origin)['status'] == 'unconfirmed'
    assert .08 < time.monotonic()-start < .8
    assert len(requests) == 1


@pytest.mark.parametrize('framing', ['length', 'chunked'])
@pytest.mark.parametrize('delta', [0, 1])
def test_exact_response_budget(receiver, framing, delta):
    replies = fx.responses()
    body = json.dumps(replies[3], separators=(',', ':')).encode()
    replies[3]['text'] += 'x' * (receiver.RESPONSE_LIMIT+delta-len(body))
    raw = json.dumps(replies[3], separators=(',', ':')).encode()
    assert len(raw) == receiver.RESPONSE_LIMIT+delta
    if framing == 'chunked':
        replies[3] = fx.reply(hex(len(raw))[2:].encode()+b'\r\n'+raw+b'\r\n0\r\n\r\n', b'Transfer-Encoding: chunked\r\n')
    else:
        replies[3] = fx.reply(raw)
    with fx.server(replies) as (origin, requests):
        assert run(receiver, origin)['status'] == ('completed' if delta == 0 else 'unconfirmed')
    assert len(requests) == (6 if delta == 0 else 4)


@pytest.mark.parametrize('phase', ['connect', 'tls', 'send', 'read'])
def test_io_errors_have_no_original_exception_context(receiver, monkeypatch, phase):
    class Socket:
        def settimeout(self, value): pass
        def connect(self, address):
            if phase == 'connect': raise OSError(fx.SECRET)
        def send(self, data):
            if phase == 'send': raise OSError(fx.SECRET)
            return len(data)
        def recv(self, size): raise OSError(fx.TEXT)
        def close(self): pass
    class Context:
        def wrap_socket(self, *a, **kw): raise OSError(fx.TOKEN)
    monkeypatch.setattr(receiver.socket, 'socket', lambda *a: Socket())
    monkeypatch.setattr(receiver.ssl, 'create_default_context', lambda: Context())
    cfg = receiver.Config.from_mapping(fx.config(('https' if phase == 'tls' else 'http')+'://127.0.0.1:1'))
    with pytest.raises(receiver.SafeFailure) as caught:
        receiver.FixedWire(cfg).claim(cfg)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert all(s not in repr(caught.value) for s in (fx.SECRET, fx.TEXT, fx.TOKEN))


@pytest.mark.parametrize('field', ['protocol', 'candidate_kind', 'declassification_status', 'rule_version',
                                  'source_proof_digest', 'policy_binding', 'projection_digest'])
def test_remaining_security_labels_and_versions_are_exact(receiver, field):
    replies = fx.responses()
    replies[3][field] = 'unknown'
    with fx.server(replies) as (origin, requests):
        assert run(receiver, origin)['status'] == 'unconfirmed'
    assert len(requests) == 4


@pytest.mark.parametrize('value,count', [(None, 0), ('', 0), ('候选', 1)])
def test_nullable_text_preserves_field_count_without_output(receiver, value, count):
    replies = fx.responses()
    replies[3]['text'] = value
    with fx.server(replies) as (origin, requests):
        result = run(receiver, origin)
    assert result == dict(status='completed', receipt_id=fx.RECEIPT, received_fields=count)
    assert len(requests) == 6


@pytest.mark.parametrize('fault,operations', [('capability',2), ('ack',5), ('batch',3)])
def test_no_downstream_operation_after_protocol_rejection(receiver, fault, operations):
    replies = fx.responses()
    if fault == 'capability': replies[1]['capabilities'][0]['allowed'] = False
    if fault == 'ack': replies[4]['accepted_sequence'] = 2
    if fault == 'batch': replies[2]['batch_id'] = None
    with fx.server(replies) as (origin, requests):
        assert run(receiver, origin)['status'] == 'unconfirmed'
    assert len(requests) == operations


def test_finish_is_one_shot_even_after_success(receiver):
    with fx.server([fx.responses()[-1]]) as (origin, requests):
        cfg = receiver.Config.from_mapping(fx.config(origin))
        wire = receiver.FixedWire(cfg)
        claim = receiver.ClaimView(fx.RUN, fx.TASK, fx.TOKEN)
        assert wire.finish_once(claim).status == 'completed'
        with pytest.raises(receiver.SafeFailure):
            wire.finish_once(claim)
    assert len(requests) == 1


def test_no_external_dns_and_exact_fixed_defaults(receiver, monkeypatch):
    assert receiver.OPERATION_SECONDS == 10
    assert receiver.REQUEST_LIMIT == 64 * 1024 and receiver.RESPONSE_LIMIT == 256 * 1024
    def forbidden(*a, **kw): pytest.fail('DNS resolution attempted')
    monkeypatch.setattr(receiver.socket, 'getaddrinfo', forbidden)
    with fx.server(fx.responses()) as (origin, requests):
        assert run(receiver, origin)['status'] == 'completed'
    assert len(requests) == 6
