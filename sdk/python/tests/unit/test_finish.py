"""Finish confirms complete, bound success or reports uncertainty, never retries."""
import json

import pytest

from codec_fixtures import U, V, SECRET, deny_network
from test_client import make_client, invoke


def test_finish_response_budget_guard_is_inside_unknown_boundary(monkeypatch):
    from openqms_agent_sdk import UnknownOutcome
    from openqms_agent_sdk.models import WireResponse
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()
    wire.fault = lambda op: WireResponse(200, b' ' * (parent._config.response_budget + 1), True)
    with pytest.raises(UnknownOutcome) as raised:
        run.finish(status='completed')
    assert raised.value.outcome_unknown is True
    assert run.state == 'uncertain'
    assert len(wire.calls) == 1


@pytest.mark.parametrize('status', [301, 302, 307, 308, 500, 502, 503, 504, 418, 429])
def test_finish_non_success_wire_status_is_unknown_even_with_valid_json(monkeypatch, status):
    from openqms_agent_sdk import UnknownOutcome
    from openqms_agent_sdk.models import WireResponse
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()
    body = json.dumps(wire.responses['finish']).encode()
    wire.fault = lambda op: WireResponse(status, body, True)
    with pytest.raises(UnknownOutcome) as raised:
        run.finish(status='completed')
    assert raised.value.status == status
    assert raised.value.may_have_been_sent
    assert len(wire.calls) == 1


@pytest.mark.parametrize('fault', [
    'oversize', 'utf8', 'json', 'duplicate', 'nan', 'schema', 'wrong_run',
    'wrong_task', 'status', 'timeout', 'disconnect', 'redirect', '500', '503',
    'encoding', 'read_budget',
])
def test_finish_post_send_failures_are_sanitized_unknown_without_retry(monkeypatch, fault):
    import openqms_agent_sdk as sdk
    from openqms_agent_sdk.models import WireResponse
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()
    bodies = {
        'oversize': b' ' * (parent._config.response_budget + 1),
        'utf8': b'\xff', 'json': SECRET.encode(),
        'duplicate': b'{"task_id":1,"task_id":2}', 'nan': b'{"x":NaN}',
        'schema': b'{}',
    }
    if fault in ('wrong_run', 'wrong_task', 'status'):
        body = dict(wire.responses['finish'])
        field, value = {
            'wrong_run': ('run_id', str(V)), 'wrong_task': ('task_id', str(U)),
            'status': ('task_status', 'failed'),
        }[fault]
        body[field] = value
        bodies[fault] = json.dumps(body).encode()

    def fail(op):
        if fault in bodies:
            return WireResponse(200, bodies[fault], True)
        cls, kind, status = {
            'timeout': (sdk.RequestTimeout, 'timeout', None),
            'disconnect': (sdk.TransportError, 'connection_closed', 200),
            'redirect': (sdk.HTTPError, 'redirect', 307),
            '500': (sdk.HTTPError, 'http_status', 500),
            '503': (sdk.HTTPError, 'http_status', 503),
            'encoding': (sdk.ProtocolError, 'unsupported_encoding', 200),
            'read_budget': (sdk.ResponseTooLarge, 'response_too_large', 200),
        }[fault]
        # Even unsafe exception context from a collaborator must not escape.
        try:
            raise ValueError(SECRET)
        except ValueError:
            raise cls(op, kind=kind, status=status, may_have_been_sent=True)

    wire.fault = fail
    with pytest.raises(sdk.UnknownOutcome) as raised:
        run.finish(status='completed')
    error = raised.value
    assert error.outcome_unknown and error.may_have_been_sent
    assert error.__cause__ is None and error.__context__ is None
    assert SECRET not in str(error) + repr(error) + repr(error.args) + repr(vars(error))
    assert run.state == 'uncertain'
    assert run._token is None
    assert len(wire.calls) == 1
    with pytest.raises(sdk.ClientClosed):
        run.finish(status='completed')
    assert len(wire.calls) == 1


@pytest.mark.parametrize('status', [400, 401, 403, 404, 409, 410, 422])
@pytest.mark.parametrize('wire_response', [False, True])
def test_explicit_v1_rejection_is_http_error_not_unknown(monkeypatch, status, wire_response):
    from openqms_agent_sdk import HTTPError
    from openqms_agent_sdk.models import WireResponse
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()

    def reject(op):
        if wire_response:
            return WireResponse(status, b'\xff' + SECRET.encode(), True)
        raise HTTPError(op, kind='http_status', status=status, may_have_been_sent=True)

    wire.fault = reject
    with pytest.raises(HTTPError) as raised:
        run.finish(status='completed')
    assert not raised.value.outcome_unknown
    assert raised.value.status == status
    assert run.state == 'open'
    assert len(wire.calls) == 1


@pytest.mark.parametrize('kind', ['dns', 'tls', 'connection'])
def test_proven_pre_send_transport_failure_is_not_unknown(monkeypatch, kind):
    from openqms_agent_sdk import TransportError
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()

    def fail(op):
        raise TransportError(op, kind=kind, may_have_been_sent=False)

    wire.fault = fail
    with pytest.raises(TransportError) as raised:
        run.finish(status='completed')
    assert not raised.value.outcome_unknown
    assert not raised.value.may_have_been_sent
    assert run.state == 'open'
    assert len(wire.calls) == 1  # Enter exchange, but no HTTP bytes sent.


@pytest.mark.parametrize('status', ['completed', 'failed'])
def test_valid_finish_closes_and_clears_token_then_all_operations_are_local(monkeypatch, status):
    from openqms_agent_sdk import ClientClosed
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.responses['finish'].update(task_status=status, run_status=status)
    wire.calls.clear()
    result = run.finish(status=status)
    assert result.task_status == result.run_status == status
    assert run.state == 'closed_successfully' and run._token is None
    assert len(wire.calls) == 1
    for op in tuple(wire.responses)[1:]:
        with pytest.raises(ClientClosed):
            invoke(run, op)
    assert len(wire.calls) == 1


def test_invalid_finish_is_local_no_exchange(monkeypatch):
    from openqms_agent_sdk import ValidationError
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()
    with pytest.raises(ValidationError) as raised:
        run.finish(status=SECRET)
    assert not raised.value.may_have_been_sent and not raised.value.outcome_unknown
    assert wire.calls == [] and run.state == 'open'
