"""Client credential domains, safe failures, single deadlines and local ownership."""
import json

import pytest

from codec_fixtures import U, V, deny_network, response_cases
from test_client import FakeTransport, invoke, make_client


INSTALLATION_SECRET = 'installation-secret-sentinel'
RUN_TOKEN = 'opaque-not-a-jwt-run-token-sentinel'
REQUEST_KEY = 'caller-request-key-sentinel'
PAYLOAD = 'private-payload-sentinel'


def assert_safe(error):
    diagnostics = str(error) + repr(error) + repr(error.args) + repr(vars(error))
    for sentinel in (INSTALLATION_SECRET, RUN_TOKEN, REQUEST_KEY, PAYLOAD):
        assert sentinel not in diagnostics
    assert error.__cause__ is None and error.__context__ is None
    assert not hasattr(error, 'original') and not hasattr(error, 'response')


def test_credentials_keys_and_payloads_have_distinct_domains(monkeypatch):
    from openqms_agent_sdk import client, ClientConfig, EventPayload
    monkeypatch.setattr(client, 'Transport', FakeTransport)
    parent = client.InstallationClient(ClientConfig('https://example.invalid'), U, INSTALLATION_SECRET)
    wire = parent._transport
    wire.responses['claim']['token'] = RUN_TOKEN
    run = parent.claim_run(request_key=REQUEST_KEY)
    op, token, request, _ = wire.calls[0]
    assert op == 'claim' and token is None
    assert json.loads(request.body) == dict(installation_id=str(U), secret=INSTALLATION_SECRET, request_key=REQUEST_KEY)
    wire.calls.clear()
    run.record_event(idempotency_key='event-key', event_type='progress', payload=EventPayload(message=PAYLOAD))
    _, token, request, _ = wire.calls[0]
    assert token == RUN_TOKEN
    assert json.loads(request.body)['payload']['message'] == PAYLOAD
    assert INSTALLATION_SECRET.encode() not in request.body
    assert RUN_TOKEN.encode() not in request.body
    assert REQUEST_KEY.encode() not in request.body
    for obj in (parent, run, run.claim, request):
        assert all(s not in repr(obj) + str(obj) for s in (INSTALLATION_SECRET, RUN_TOKEN, REQUEST_KEY, PAYLOAD))


@pytest.mark.parametrize('operation', tuple(response_cases()))
def test_each_operation_uses_one_deadline_from_before_encode_through_binding(monkeypatch, operation):
    from openqms_agent_sdk import client
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()
    events, deadlines = [], []
    encode, decode = client._codec.encode_request, client._codec.decode_response

    class TracedDeadline:
        def __init__(self, timeout, op):
            self.operation = op
            deadlines.append(self)
            events.append('deadline')
            assert timeout == parent._config.timeout

        def check(self):
            events.append('check')

    def encoded(op, parameters):
        events.append('encode')
        return encode(op, parameters)

    def exchanged(op, *, token, request, deadline):
        from openqms_agent_sdk.models import WireResponse
        assert deadline is deadlines[0]
        events.append('exchange')
        return WireResponse(200, json.dumps(wire.responses[op]).encode(), True)

    def decoded(op, body, **context):
        events.append('decode')
        if op != 'claim':
            assert context['run_id'] == U and context['task_id'] == V
        if op == 'finish':
            assert context['finish_status'] == 'completed'
        if op == 'capa_context':
            assert context['view'] == 'report' and context['report_id'] == V
        result = decode(op, body, **context)
        events.append('binding_complete')
        return result

    monkeypatch.setattr(client, 'Deadline', TracedDeadline)
    monkeypatch.setattr(client._codec, 'encode_request', encoded)
    monkeypatch.setattr(client._codec, 'decode_response', decoded)
    monkeypatch.setattr(wire, 'exchange', exchanged)
    if operation == 'claim':
        parent.claim_run(request_key='key')
    else:
        invoke(run, operation)
    assert len(deadlines) == 1
    assert events == ['deadline', 'encode', 'check', 'exchange', 'check', 'decode', 'binding_complete', 'check']


@pytest.mark.parametrize('operation', ['claim', 'finish'])
@pytest.mark.parametrize('status', [400, 503])
def test_non_success_wire_still_checks_shared_deadline_without_decoding(monkeypatch, operation, status):
    from openqms_agent_sdk import client, HTTPError, UnknownOutcome
    from openqms_agent_sdk.models import WireResponse
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    checks = []

    class TracedDeadline:
        def __init__(self, timeout, op):
            self.operation = op

        def check(self):
            checks.append(self)

    def forbidden_decode(*args, **kwargs):
        pytest.fail('HTTP error bodies must never be decoded')

    monkeypatch.setattr(client, 'Deadline', TracedDeadline)
    monkeypatch.setattr(client._codec, 'decode_response', forbidden_decode)
    wire.fault = lambda op: WireResponse(status, PAYLOAD.encode(), True)
    cls = UnknownOutcome if operation == 'finish' and status == 503 else HTTPError
    with pytest.raises(cls):
        parent.claim_run(request_key='key') if operation == 'claim' else run.finish(status='completed')
    assert len(checks) == 2 and checks[0] is checks[1]


@pytest.mark.parametrize('phase', ['encode', 'after_exchange', 'after_binding'])
@pytest.mark.parametrize('operation', ['capabilities', 'finish'])
def test_deadline_expiry_at_each_boundary_keeps_send_and_finish_semantics(monkeypatch, phase, operation):
    from openqms_agent_sdk import client, RequestTimeout, UnknownOutcome
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()
    target = {'encode': 1, 'after_exchange': 2, 'after_binding': 3}[phase]

    class ExpiringDeadline:
        def __init__(self, timeout, op):
            self.operation = op
            self.checks = 0

        def check(self):
            self.checks += 1
            if self.checks == target:
                raise RequestTimeout(self.operation, kind='deadline')

    monkeypatch.setattr(client, 'Deadline', ExpiringDeadline)
    unknown = operation == 'finish' and phase != 'encode'
    with pytest.raises(UnknownOutcome if unknown else RequestTimeout) as caught:
        invoke(run, operation)
    assert_safe(caught.value)
    assert caught.value.may_have_been_sent is (phase != 'encode')
    assert caught.value.outcome_unknown is unknown
    assert len(wire.calls) == (0 if phase == 'encode' else 1)
    assert run.state == ('uncertain' if unknown else 'open')
    if unknown:
        assert run._token is None


@pytest.mark.parametrize('operation', ['claim', 'save_result', 'finish'])
def test_encode_budget_failure_is_sanitized_before_any_exchange(monkeypatch, operation):
    from openqms_agent_sdk import client, ValidationError
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()

    def fail(op, parameters):
        try:
            raise ValueError(PAYLOAD)
        except ValueError:
            raise ValidationError(op, kind='request_too_large')

    monkeypatch.setattr(client._codec, 'encode_request', fail)
    with pytest.raises(ValidationError) as caught:
        parent.claim_run(request_key=REQUEST_KEY) if operation == 'claim' else invoke(run, operation)
    assert_safe(caught.value)
    assert not caught.value.may_have_been_sent and not caught.value.outcome_unknown
    assert wire.calls == [] and run.state == 'open'


@pytest.mark.parametrize('operation', ['claim', 'record_event', 'finish'])
def test_configured_response_budget_applies_before_json_even_for_valid_wire(monkeypatch, operation):
    from openqms_agent_sdk import ClientConfig, ResponseTooLarge, UnknownOutcome
    from openqms_agent_sdk.models import WireResponse
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    parent._config = ClientConfig('https://example.invalid', response_budget=65536)
    wire.calls.clear()
    body = json.dumps(wire.responses[operation]).encode() + b' ' * 65536
    wire.fault = lambda op: WireResponse(200, body, True)
    with pytest.raises(UnknownOutcome if operation == 'finish' else ResponseTooLarge) as caught:
        parent.claim_run(request_key='key') if operation == 'claim' else invoke(run, operation)
    assert_safe(caught.value)
    assert caught.value.may_have_been_sent and caught.value.status == 200
    assert len(wire.calls) == 1


@pytest.mark.parametrize('operation', ['claim', 'capabilities', 'record_event', 'finish'])
def test_transport_failure_discards_unsafe_exception_context(monkeypatch, operation):
    from openqms_agent_sdk import TransportError, UnknownOutcome
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()

    def fail(op):
        try:
            raise RuntimeError(PAYLOAD + RUN_TOKEN + INSTALLATION_SECRET + REQUEST_KEY)
        except RuntimeError:
            error = TransportError(op, kind='connection_closed', may_have_been_sent=True)
            error.response = object()
            raise error

    wire.fault = fail
    with pytest.raises(UnknownOutcome if operation == 'finish' else TransportError) as caught:
        parent.claim_run(request_key=REQUEST_KEY) if operation == 'claim' else invoke(run, operation)
    assert_safe(caught.value)
    assert caught.value.may_have_been_sent
    assert caught.value.outcome_unknown is (operation == 'finish')
    assert len(wire.calls) == 1  # Other writes may also have reached the platform.


def test_run_close_is_local_and_parent_alone_owns_shared_transport(monkeypatch):
    from openqms_agent_sdk import ClientClosed
    parent, wire = make_client(monkeypatch)
    first = parent.claim_run(request_key='first')
    second = parent.claim_run(request_key='second')
    wire.calls.clear()
    closes = []
    original_close = wire.close

    def closed():
        closes.append(True)
        original_close()

    monkeypatch.setattr(wire, 'close', closed)
    first.close()
    first.close()
    assert first.state == 'closed' and first._token is None
    assert not wire.closed and wire.calls == [] and closes == []
    for op in tuple(wire.responses)[1:]:
        with pytest.raises(ClientClosed):
            invoke(first, op)
    second.capabilities()
    assert len(wire.calls) == 1 and not wire.closed
    parent.close()
    parent.close()
    assert closes == [True] and parent._secret is None
    with pytest.raises(ClientClosed):
        second.capabilities()
    with pytest.raises(ClientClosed):
        parent.claim_run(request_key='third')
    assert len(wire.calls) == 1


def test_no_automatic_permissions_ack_poll_retry_or_user_api(monkeypatch):
    from openqms_agent_sdk import InstallationClient, RunClient
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()
    wire.responses['capabilities']['capabilities'][0]['allowed'] = False
    run.capabilities()
    run.claim_messages()
    run.message_history()
    run.capabilities()
    assert [call[0] for call in wire.calls] == ['capabilities', 'claim_messages', 'message_history', 'capabilities']
    assert json.loads(wire.calls[1][2].body) == {'limit': 20}
    assert dict(wire.calls[2][2].query) == {'after_sequence': '0', 'limit': '20'}
    forbidden = {'request', 'get', 'post', 'login', 'user', 'admin', 'renew', 'reclaim', 'retry', 'poll', 'execute_message', 'decode_token', 'refresh_token'}
    for cls in (InstallationClient, RunClient):
        assert not forbidden & set(dir(cls))
