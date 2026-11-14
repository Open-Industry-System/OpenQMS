"""Fixed local D4 receiver. Standard library only; never prints delivered text.

This is a deployment-hashed executable, not a general HTTP client or SDK.
"""
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
import socket
import ssl
import sys
import time
from urllib.parse import urlsplit
from uuid import UUID

START_MESSAGE = 'deliver_d4_root_cause_candidate_v1'
TEXT_CAPABILITY = 'capa.d4.root_cause_candidate.masked.v1'
TEXT_PROFILE = 'local_d4_root_cause_text_v1'
REQUEST_LIMIT = 64 * 1024
RESPONSE_LIMIT = 256 * 1024
HEADER_LIMIT = 32 * 1024
OPERATION_SECONDS = 10
LABELS = {
    'protocol': '1', 'projection_id': TEXT_CAPABILITY, 'data_class': 'restricted',
    'projection': 'masked', 'candidate_kind': 'redaction_candidate',
    'declassification_status': 'not_approved', 'source_proof': 'employee_declared_complete_v1',
    'source_authorization': 'current', 'model_delivery_allowed': False,
    'delivery_scope': 'local_plugin_only', 'rule_version': 'capa.d4.redaction.v1',
    'field': 'd4_root_cause',
}
VERSIONS = ('source_version', 'source_proof_digest', 'policy_binding', 'projection_digest')
ROUTES = {
    'claim': ('POST', 'claim'), 'capabilities': ('GET', 'capabilities'),
    'start': ('POST', 'messages/claim'), 'body': ('GET', 'capa/d4/root-cause-text'),
    'ack': ('POST', 'messages/ack'), 'finish': ('POST', 'finish'),
}


class SafeFailure(Exception):
    def __init__(self, status='unconfirmed'):
        self.status = status
        super().__init__(status)


def require(condition):
    if not condition:
        raise SafeFailure()


def text(value, minimum=0, maximum=RESPONSE_LIMIT):
    require(type(value) is str and minimum <= len(value) <= maximum)
    return value


def uuid(value):
    text(value, 36, 36)
    require(str(UUID(value)) == value)
    return value


def integer(value, minimum=0):
    require(type(value) is int and minimum <= value <= 2**63-1)
    return value


def timestamp(value):
    parsed = datetime.fromisoformat(text(value, 1, 100).replace('Z', '+00:00'))
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None)


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result
    def invalid(_):
        raise SafeFailure()
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)
    require(type(value) is dict)
    return value


def origin_parts(origin):
    text(origin, 1, 200)
    require(not any(ord(c) <= 32 or ord(c) >= 127 for c in origin))
    require(not any(c in origin for c in ('?', '#', '\\')))
    p = urlsplit(origin)
    require(p.scheme in ('http', 'https') and p.hostname in ('127.0.0.1', '::1'))
    require(p.username is None and p.password is None and p.path == '')
    port = p.port or (443 if p.scheme == 'https' else 80)
    require(1 <= port <= 65535)
    authority = ('['+p.hostname+']') if p.hostname == '::1' else p.hostname
    require(p.netloc in (authority, authority+':'+str(port)))
    return p.hostname, port, p.scheme == 'https'


@dataclass(frozen=True, slots=True, repr=False)
class Config:
    origin: str
    tenant_slug: str
    installation_id: str
    secret: str
    request_key: str
    expected_report_id: str

    @classmethod
    def from_mapping(cls, value):
        valid = None
        try:
            require(type(value) is dict and set(value) == set(cls.__dataclass_fields__))
            origin_parts(value['origin'])
            require(re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', text(value['tenant_slug'])) is not None)
            uuid(value['installation_id'])
            uuid(value['expected_report_id'])
            text(value['secret'], 20, 200)
            text(value['request_key'], 1, 100)
            valid = cls(**value)
        except Exception:
            pass
        if valid is None:
            raise SafeFailure('configuration_invalid')
        return valid


@dataclass(frozen=True, slots=True)
class ClaimView:
    run_id: str
    task_id: str
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MessageView:
    message_id: str
    sequence: int
    content: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class BatchView:
    batch_id: str | None
    messages: tuple


@dataclass(frozen=True, slots=True)
class DeliveryView:
    receipt_id: str
    report_id: str
    run_id: str
    task_id: str
    recipient_installation_id: str
    text: str | None = field(repr=False)
    labels: tuple
    versions: tuple
    deadline: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class FinishView:
    run_id: str
    task_id: str
    status: str


class Deadline:
    def __init__(self):
        self.end = time.monotonic() + OPERATION_SECONDS

    def remaining(self):
        remaining = self.end - time.monotonic()
        require(remaining > 0)
        return remaining

    def check(self):
        self.remaining()


class RawReader:
    """Buffer only above deadline-checked raw socket reads (also for TLS)."""
    def __init__(self, sock, deadline):
        self.sock, self.deadline, self.buffer = sock, deadline, b''

    def more(self):
        self.sock.settimeout(self.deadline.remaining())
        data = self.sock.recv(4096)
        self.deadline.check()
        require(bool(data))
        self.buffer += data

    def exact(self, size):
        while len(self.buffer) < size:
            self.more()
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result

    def line(self, limit):
        while b'\r\n' not in self.buffer:
            require(len(self.buffer) < limit)
            self.more()
        index = self.buffer.index(b'\r\n') + 2
        require(index <= limit)
        return self.exact(index)


def read_headers(reader):
    headers, total = {}, 0
    for _ in range(101):
        line = reader.line(HEADER_LIMIT)
        total += len(line)
        require(total <= HEADER_LIMIT)
        if line == b'\r\n':
            return headers
        name, separator, value = line[:-2].partition(b':')
        require(bool(separator) and re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is not None)
        require(not any(c < 32 and c != 9 or c == 127 for c in value))
        name = name.lower()
        require(name not in headers)
        headers[name] = value.strip(b' \t')
    raise SafeFailure()


def response_bytes(reader, body_operation):
    status_line = reader.line(4096)
    require(re.fullmatch(rb'HTTP/1\.[01] [1-5][0-9]{2} [\x20-\x7e]*\r\n', status_line) is not None)
    status = int(status_line.split(b' ')[1])
    headers = read_headers(reader)
    # An explicit error status is a rejection, never a remote terminal-state claim.
    if not 200 <= status < 300:
        raise SafeFailure('rejected' if status in (400, 401, 403, 404, 409, 410, 422) else 'unconfirmed')
    require(headers.get(b'content-type', b'').split(b';')[0].strip().lower() == b'application/json')
    require(headers.get(b'content-encoding', b'identity').lower() == b'identity')
    if body_operation:
        require(headers.get(b'cache-control', b'').lower() == b'no-store')
    length, transfer = headers.get(b'content-length'), headers.get(b'transfer-encoding')
    require(not (length is not None and transfer is not None))
    if transfer is not None:
        require(transfer.lower() == b'chunked')
        pieces, total = [], 0
        while True:
            line = reader.line(4096)
            number, _, extension = line[:-2].partition(b';')
            require(re.fullmatch(rb'[0-9a-fA-F]{1,16}', number) is not None)
            require(all(32 <= c <= 126 for c in extension))
            size = int(number, 16)
            if size == 0:
                # Trailers are bounded and syntactically checked; never metadata overrides.
                trailers = read_headers(reader)
                require(not set(trailers) & {b'content-length', b'transfer-encoding', b'content-type', b'content-encoding'})
                return b''.join(pieces)
            total += size
            require(total <= RESPONSE_LIMIT)
            pieces.append(reader.exact(size))
            require(reader.exact(2) == b'\r\n')
    require(length is not None and re.fullmatch(rb'[0-9]{1,20}', length) is not None)
    size = int(length)
    require(size <= RESPONSE_LIMIT)
    return reader.exact(size)


def send_all(sock, raw, deadline, state):
    view = memoryview(raw)
    while view:
        sock.settimeout(deadline.remaining())
        state['sent'] = True
        count = sock.send(view)
        deadline.check()
        require(count > 0)
        view = view[count:]


class FixedWire:
    def __init__(self, config):
        self.config = config
        self.finish_attempted = False

    def _operation(self, operation, claim, payload, decode):
        deadline = Deadline()  # Starts before encoding or schema work.
        state, sock, result, failure = {'sent': False}, None, None, None
        try:
            host, port, tls = origin_parts(self.config.origin)
            method, path = ROUTES[operation]
            body = b'' if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
            host_header = ('['+host+']') if host == '::1' else host
            headers = [f'{method} /api/agent/runtime/{path} HTTP/1.1', f'Host: {host_header}:{port}',
                       'Connection: close', 'Accept: application/json', 'Content-Type: application/json',
                       'X-Tenant-ID: '+self.config.tenant_slug, 'Content-Length: '+str(len(body))]
            if claim is not None:
                require(all(32 < ord(c) < 127 for c in text(claim.token, 1)))
                headers.append('Authorization: Bearer '+claim.token)
            raw = ('\r\n'.join(headers)+'\r\n\r\n').encode('ascii')+body
            require(len(raw) <= REQUEST_LIMIT)
            deadline.check()
            sock = socket.socket(socket.AF_INET6 if host == '::1' else socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(deadline.remaining())
            sock.connect((host, port))
            deadline.check()
            if tls:
                context = ssl.create_default_context()
                deadline.check()
                sock = context.wrap_socket(sock, server_hostname=host, do_handshake_on_connect=False)
                sock.settimeout(deadline.remaining())
                sock.do_handshake()
                deadline.check()
            send_all(sock, raw, deadline, state)
            raw = response_bytes(RawReader(sock, deadline), operation == 'body')
            deadline.check()
            data = parse_json(raw)
            deadline.check()
            result = decode(data, deadline)
            deadline.check()
        except Exception as exc:
            failure = 'rejected' if isinstance(exc, SafeFailure) and exc.status == 'rejected' else 'unconfirmed'
            if operation == 'finish' and state['sent'] and failure != 'rejected':
                failure = 'unknown'
        finally:
            if sock is not None:
                sock.close()
        if failure is None:
            try:
                deadline.check()
            except Exception:
                failure = 'unknown' if operation == 'finish' and state['sent'] else 'unconfirmed'
        if failure is not None:
            raise SafeFailure(failure)
        return result

    def claim(self, config):
        def decode(p, deadline):
            integer(p['lease_epoch'])
            integer(p['accepted_message_seq'])
            require(type(p['has_resume_checkpoint']) is bool)
            timestamp(p['lease_expires_at'])
            return ClaimView(uuid(p['run_id']), uuid(p['task_id']), text(p['token'], 1))
        return self._operation('claim', None, dict(installation_id=config.installation_id,
                               secret=config.secret, request_key=config.request_key), decode)

    def require_body_capability(self, claim):
        def decode(p, deadline):
            require(type(p['capabilities']) is list)
            seen = set()
            found = False
            for item in p['capabilities']:
                name = text(item['id'], 1)
                require(name not in seen)
                seen.add(name)
                require(type(item['allowed']) is bool and type(item['required']) is bool)
                require(item['projection'] in (None, 'masked', 'raw'))
                if name == TEXT_CAPABILITY:
                    found = item['allowed'] is True and item['projection'] == 'masked'
            require(found)
        self._operation('capabilities', claim, None, decode)

    def claim_start(self, claim, *, limit=1):
        require(type(limit) is int and limit == 1)
        def decode(p, deadline):
            accepted = integer(p['accepted_sequence'])
            require(type(p['messages']) is list and len(p['messages']) <= 1)
            messages = tuple(MessageView(uuid(m['message_id']), integer(m['sequence'], 1), text(m['content'])) for m in p['messages'])
            batch_id = None if p['batch_id'] is None else uuid(p['batch_id'])
            require(not messages or batch_id is not None and messages[0].sequence > accepted)
            return BatchView(batch_id, messages)
        return self._operation('start', claim, {'limit': 1}, decode)

    def read_body(self, claim):
        def decode(p, deadline):
            for key, expected in LABELS.items():
                require(type(p[key]) is type(expected) and p[key] == expected)
            versions = tuple(text(p[key], 64, 64) for key in VERSIONS)
            require(all(re.fullmatch(r'[a-f0-9]{64}', v) for v in versions))
            text(p['plugin_version'], 1, 100)
            timestamp(p['generated_at'])
            require(p['text'] is None or type(p['text']) is str)
            delivery = DeliveryView(uuid(p['receipt_id']), uuid(p['report_id']), uuid(p['run_id']),
                uuid(p['task_id']), uuid(p['recipient_installation_id']), p['text'], tuple(LABELS.items()), versions, deadline)
            self.validate_delivery(claim, self.config, delivery)
            return delivery
        return self._operation('body', claim, None, decode)

    def validate_delivery(self, claim, config, delivery):
        delivery.deadline.check()
        require(delivery.run_id == claim.run_id and delivery.task_id == claim.task_id)
        require(delivery.report_id == config.expected_report_id and delivery.recipient_installation_id == config.installation_id)
        require(delivery.labels == tuple(LABELS.items()))
        delivery.deadline.check()

    def ack_start(self, claim, batch):
        require(len(batch.messages) == 1 and batch.messages[0].content == START_MESSAGE)
        def decode(p, deadline):
            require(integer(p['accepted_sequence']) == batch.messages[0].sequence)
        self._operation('ack', claim, dict(batch_id=batch.batch_id, through_sequence=batch.messages[0].sequence), decode)

    def finish_once(self, claim):
        require(not self.finish_attempted)
        self.finish_attempted = True
        def decode(p, deadline):
            require(uuid(p['run_id']) == claim.run_id and uuid(p['task_id']) == claim.task_id)
            require(p['run_status'] == p['task_status'] == 'completed')
            integer(p['lease_epoch'])
            return FinishView(claim.run_id, claim.task_id, 'completed')
        return self._operation('finish', claim, {'status': 'completed'}, decode)


def receive_once(wire, config):
    claim = wire.claim(config)
    wire.require_body_capability(claim)
    batch = wire.claim_start(claim, limit=1)
    if len(batch.messages) != 1 or batch.messages[0].content != START_MESSAGE:
        return {'status': 'input_unconfirmed', 'received_fields': 0}
    delivery = wire.read_body(claim)
    wire.validate_delivery(claim, config, delivery)
    wire.ack_start(claim, batch)
    wire.finish_once(claim)
    return {'status': 'completed', 'receipt_id': delivery.receipt_id,
            'received_fields': int(delivery.text not in (None, ''))}


def safe_receive(wire, config):
    try:
        return receive_once(wire, config)
    except SafeFailure as exc:
        return {'status': exc.status, 'received_fields': 0}
    except Exception:
        return {'status': 'unconfirmed', 'received_fields': 0}


def main():
    result = {'status': 'configuration_invalid', 'received_fields': 0}
    try:
        raw = sys.stdin.buffer.read(REQUEST_LIMIT+1)
        require(len(raw) <= REQUEST_LIMIT)
        config = Config.from_mapping(parse_json(raw))
        result = safe_receive(FixedWire(config), config)
    except Exception:
        pass
    print(json.dumps(result, separators=(',', ':')))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    sys.exit(main())
