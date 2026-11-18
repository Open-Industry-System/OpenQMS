"""Fixed D4 source-grant revocation witness for the synthetic receiver case."""
import json
import re
import socket
import ssl
import time


RUNTIME_BODY = '/api/agent/runtime/capa/d4/root-cause-text'
INVALID_RUN = {'detail': 'Invalid run credential'}


class Deadline:
    def __init__(self, end):
        self.end = end

    def remaining(self):
        seconds = self.end - time.monotonic()
        if seconds <= 0:
            raise TimeoutError('D4 revocation witness timed out')
        return seconds

    def check(self):
        self.remaining()


def request(worker, config, method, route, token, payload, deadline, *, status, limit, no_store=False):
    # Inputs are limited to fixed callers below. Use the reviewed receiver's
    # bounded raw I/O so a slow response cannot extend the case deadline.
    host, port, tls = worker.origin_parts(config.origin)
    authority = '[::1]' if host == '::1' else host
    worker.require(re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', config.tenant_slug) is not None)
    authorization = ''
    if token is not None:
        worker.require(isinstance(token, str) and 1 <= len(token) <= 8192
                       and all(32 < ord(c) < 127 for c in token))
        authorization = f'Authorization: Bearer {token}\r\n'
    raw = b'' if payload is None else json.dumps(payload, separators=(',', ':')).encode('ascii')
    headers = (
        f'{method} {route} HTTP/1.1\r\nHost: {authority}:{port}\r\n'
        f'{authorization}X-Tenant-ID: {config.tenant_slug}\r\n'
        'Connection: close\r\nAccept: application/json\r\nContent-Type: application/json\r\n'
        f'Content-Length: {len(raw)}\r\n\r\n'
    ).encode('ascii')
    with socket.socket(socket.AF_INET6 if host == '::1' else socket.AF_INET, socket.SOCK_STREAM) as connected:
        connected.settimeout(deadline.remaining())
        connected.connect((host, port))
        if tls:
            context = ssl.create_default_context()
            with context.wrap_socket(connected, server_hostname=host, do_handshake_on_connect=False) as secured:
                secured.settimeout(deadline.remaining())
                secured.do_handshake()
                return read_response(worker, secured, headers + raw, deadline, status, limit, no_store)
        return read_response(worker, connected, headers + raw, deadline, status, limit, no_store)


def read_response(worker, connection, data, deadline, status, limit, no_store):
    worker.send_all(connection, data, deadline, {'sent': False})
    reader = worker.RawReader(connection, deadline)
    line = reader.line(4096)
    worker.require(re.fullmatch(fr'HTTP/1\.[01] {status} [\x20-\x7e]*\r\n'.encode(), line) is not None)
    headers = worker.read_headers(reader)
    worker.require(headers.get(b'content-type', b'').split(b';')[0].strip().lower() == b'application/json'
                   and headers.get(b'content-encoding', b'identity').lower() == b'identity'
                   and b'transfer-encoding' not in headers)
    if no_store:
        worker.require(headers.get(b'cache-control', b'').lower() == b'no-store')
    length = headers.get(b'content-length', b'')
    worker.require(re.fullmatch(rb'[0-9]{1,9}', length) is not None and int(length) <= limit)
    payload = worker.parse_json(reader.exact(int(length)))
    deadline.check()
    return payload


def disable_grant(worker, config, admin_token, grant_id, deadline):
    worker.require(admin_token is not None)
    install_id, grant_id = worker.uuid(config.installation_id), worker.uuid(grant_id)
    route = f'/api/admin/agent-plugins/{install_id}/grants/{grant_id}'
    result = request(worker, config, 'PATCH', route, admin_token, {'enabled': False}, deadline,
                     status=200, limit=8192)
    worker.require(result.get('enabled') is False and result.get('installation_id') == install_id
                   and result.get('grant_id') == grant_id and result.get('capability_id') == worker.TEXT_CAPABILITY)


def observe_revocation(worker, config, *, admin_token, task_id, run_id, grant_id, deadline):
    """Observe a real release, then one fixed PATCH and a same-token denial.

    The caller supplies the already reviewed receiver module and private,
    synthetic tenant credentials. This does not acknowledge or finish the
    run. The broker must independently reconcile and reclaim it afterwards.
    """
    try:
        return _observe(worker, config, admin_token, task_id, run_id, grant_id, deadline)
    except Exception:
        raise ValueError('D4 revocation could not be witnessed') from None


def _observe(worker, config, admin_token, task_id, run_id, grant_id, end):
    deadline = Deadline(end)

    class Wire(worker.FixedWire):
        def _operation(self, operation, claim, payload, decode):
            worker.require(operation in ('claim', 'capabilities', 'start', 'body'))
            method, route = worker.ROUTES[operation]
            token = None if claim is None else claim.token
            data = request(worker, config, method, '/api/agent/runtime/' + route, token, payload,
                           deadline, status=200, limit=worker.RESPONSE_LIMIT,
                           no_store=operation == 'body')
            if operation == 'claim':
                worker.require(worker.integer(data['lease_epoch']) == 1
                               and worker.integer(data['accepted_message_seq']) == 0)
            result = decode(data, deadline)
            deadline.check()
            return result

    worker.uuid(task_id)
    worker.uuid(run_id)
    worker.uuid(grant_id)
    wire = Wire(config)
    claim = wire.claim(config)
    worker.require((claim.task_id, claim.run_id) == (task_id, run_id))
    wire.require_body_capability(claim)
    batch = wire.claim_start(claim, limit=1)
    worker.require(len(batch.messages) == 1 and batch.messages[0].content == worker.START_MESSAGE)
    delivery = wire.read_body(claim)
    worker.require(bool(delivery.text))
    wire.validate_delivery(claim, config, delivery)
    del delivery

    disable_grant(worker, config, admin_token, grant_id, deadline)
    denied = request(worker, config, 'GET', RUNTIME_BODY, claim.token, None, deadline,
                     status=401, limit=256)
    worker.require(denied == INVALID_RUN)
    return dict(task_id=task_id, run_id=run_id, report_id=config.expected_report_id,
                installation_id=config.installation_id, grant_id=grant_id,
                authorized_status=200, revoked_status=401, revoked_body_received=False)
