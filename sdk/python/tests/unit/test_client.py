"""Public client contract; transport is replaced before any operation."""
import importlib.util
import json

import pytest

from codec_fixtures import U, V, SECRET, deny_network, response_cases


def test_client_module_exists():
    assert importlib.util.find_spec('openqms_agent_sdk.client') is not None


class FakeTransport:
    def __init__(self, config):
        self.config = config
        self.calls = []
        self.closed = False
        self.responses = response_cases()
        self.fault = None

    def exchange(self, operation, *, token, request, deadline):
        from openqms_agent_sdk.models import WireResponse
        assert not self.closed
        self.calls.append((operation, token, request, deadline))
        if self.fault:
            return self.fault(operation)
        return WireResponse(200, json.dumps(self.responses[operation]).encode(), True)

    def close(self):
        self.closed = True


def make_client(monkeypatch):
    from openqms_agent_sdk import client, ClientConfig
    monkeypatch.setattr(client, 'Transport', FakeTransport)
    parent = client.InstallationClient(ClientConfig('https://example.invalid'), U, SECRET)
    return parent, parent._transport


def test_claim_returns_run_with_metadata_and_separate_credential(monkeypatch):
    from openqms_agent_sdk import RunClaim
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='caller-key')
    assert isinstance(run.claim, RunClaim)
    assert not hasattr(run.claim, 'token')
    op, token, request, deadline = wire.calls[0]
    assert op == 'claim' and token is None
    assert json.loads(request.body) == dict(installation_id=str(U), secret=SECRET, request_key='caller-key')
    assert deadline.operation == 'claim'
    assert SECRET not in repr(parent) + repr(run) + repr(run.claim)
    parent.close()
    assert wire.closed
    assert len(wire.calls) == 1


def invoke(run, op):
    from openqms_agent_sdk import EventPayload, ResultPayload
    return {
        'capabilities': lambda: run.capabilities(),
        'claim_messages': lambda: run.claim_messages(limit=20),
        'ack_messages': lambda: run.ack_messages(batch_id=U, through_sequence=1),
        'capa_context': lambda: run.get_capa_context(report_id=V, view='report'),
        'record_event': lambda: run.record_event(idempotency_key='event-key', event_type='progress', payload=EventPayload(message=SECRET)),
        'save_result': lambda: run.save_result(idempotency_key='result-key', payload=ResultPayload(explanations=(SECRET,)), receipt_ids=(U,)),
        'save_checkpoint': lambda: run.save_checkpoint(idempotency_key='checkpoint-key', receipt_ids=(U,)),
        'message_history': lambda: run.message_history(after_sequence=99, limit=20),
        'finish': lambda: run.finish(status='completed'),
    }[op]()


@pytest.mark.parametrize('op', tuple(response_cases())[1:])
def test_nine_run_operations_are_single_exchange_with_opaque_token(monkeypatch, op):
    import openqms_agent_sdk as sdk
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.calls.clear()
    result = invoke(run, op)
    assert type(result).__name__ == {
        'capabilities': 'Capabilities', 'claim_messages': 'MessageBatch',
        'ack_messages': 'MessageAck', 'capa_context': 'CapaContext',
        'record_event': 'RuntimeEvent', 'save_result': 'RuntimeResult',
        'save_checkpoint': 'ReadonlyCheckpoint', 'message_history': 'MessageHistory',
        'finish': 'FinishResult',
    }[op]
    assert len(wire.calls) == 1
    operation, token, request, deadline = wire.calls[0]
    assert operation == op and token == SECRET and deadline.operation == op
    if request.body:
        body = json.loads(request.body)
        assert not {'installation_id', 'secret', 'run_id', 'task_id', 'grant', 'profile'} & body.keys()
    if op == 'message_history':
        assert result.next_sequence == 3  # Behind caller cursor is valid.


@pytest.mark.parametrize('op', tuple(response_cases())[1:])
def test_parent_close_blocks_every_run_operation_locally(monkeypatch, op):
    from openqms_agent_sdk import ClientClosed
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    parent.close()
    wire.calls.clear()
    with pytest.raises(ClientClosed):
        invoke(run, op)
    assert wire.calls == []


@pytest.mark.parametrize('op', ['record_event', 'save_result', 'save_checkpoint', 'finish'])
@pytest.mark.parametrize('field', ['run_id', 'task_id'])
def test_run_response_binding_is_pinned_to_claim(monkeypatch, op, field):
    from openqms_agent_sdk import ProtocolError, UnknownOutcome
    parent, wire = make_client(monkeypatch)
    run = parent.claim_run(request_key='key')
    wire.responses[op][field] = str(V if field == 'run_id' else U)
    with pytest.raises(UnknownOutcome if op == 'finish' else ProtocolError) as raised:
        invoke(run, op)
    assert raised.value.may_have_been_sent
    assert len(wire.calls) == 2


def test_no_public_generic_or_internal_exports():
    import openqms_agent_sdk as sdk
    assert {'InstallationClient', 'RunClient'} <= set(sdk.__all__)
    assert not {'ClaimEnvelope', 'EncodedRequest', 'WireResponse', 'SUPPORTED_OPERATIONS'} & set(sdk.__all__)
    for cls in (sdk.InstallationClient, sdk.RunClient):
        assert not {'get', 'post', 'request', 'renew', 'reclaim'} & set(dir(cls))
