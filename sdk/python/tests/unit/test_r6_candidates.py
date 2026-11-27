"""D4 candidate wire contracts reject caller-selected provenance."""
import json
from uuid import UUID

import pytest
from openqms_agent_sdk import _codec
from openqms_agent_sdk.errors import ValidationError, ProtocolError
from openqms_agent_sdk.models import SUPPORTED_OPERATIONS


def test_d4_candidate_command_has_a_dedicated_registered_route():
    assert SUPPORTED_OPERATIONS.get('save_d4_candidate') == ('POST', '/api/agent/runtime/capa/d4/candidates')


def test_d4_candidate_request_carries_only_content_and_command_intent():
    request = _codec.encode_request('save_d4_candidate', dict(command_key='test', text='hypothesis',
        supporting=('D2 fact',), opposing=(), missing_information=('verify',), operation='save',
        predecessor_id=None, correction_message_id=None))
    body = json.loads(request.body)
    assert body['text'] == 'hypothesis' and body['supporting'] == ['D2 fact']
    for extra in ('report_id', 'source_ids', 'executor_id', 'receipt_ids'):
        with pytest.raises(ValidationError):
            _codec.encode_request('save_d4_candidate', dict(command_key='test', text='x', **{extra: str(UUID(int=1))}))


def test_d4_candidate_reference_validates_the_run_and_task_binding():
    run, task = UUID(int=1), UUID(int=2)
    body = dict(candidate_id=str(UUID(int=3)), command_id=str(UUID(int=4)),
        task_id=str(task), run_id=str(run), report_id=str(UUID(int=5)), state='pending', version=1)
    result = _codec.decode_response('save_d4_candidate', json.dumps(body).encode(), run_id=run, task_id=task)
    assert result.candidate_id == UUID(int=3)
    body['run_id'] = str(UUID(int=99))
    with pytest.raises(ProtocolError):
        _codec.decode_response('save_d4_candidate', json.dumps(body).encode(), run_id=run, task_id=task)


def test_d4_workflow_uses_only_turn_and_opaque_tool_ids():
    assert SUPPORTED_OPERATIONS.get('model_turn') == ('POST','/api/agent/runtime/model/infer')
    assert json.loads(_codec.encode_request('model_turn',{'turn':0}).body)=={'operation':'workflow','turn':0}
    assert json.loads(_codec.encode_request('model_tool',{'call_id':'opaque'}).body)=={'call_id':'opaque'}
    with pytest.raises(ValidationError):
        _codec.encode_request('model_turn',{'turn':0,'messages':['external']})


def test_candidate_checkpoint_reference_validates_the_binding():
    run,task=UUID(int=1),UUID(int=2)
    response=dict(checkpoint_id=str(UUID(int=3)),task_id=str(task),run_id=str(run),lease_epoch=1,
        command_watermark=2)
    result=_codec.decode_response('save_d4_checkpoint',json.dumps(response).encode(),run_id=run,task_id=task)
    assert result.command_watermark==2


def launch_wire():
    from datetime import datetime,timezone,timedelta
    return dict(protocol='r6.d4.launch.v1',profile='model_d4_candidate_v1',api_origin='http://127.0.0.1:12345',
        tenant_slug='tenant',token='synthetic-opaque-token',task_id=str(UUID(int=1)),run_id=str(UUID(int=2)),
        deployment_id=str(UUID(int=3)),lease_epoch=1,lease_expires_at=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat(),
        accepted_message_seq=0,has_resume_checkpoint=False)


def test_public_managed_launch_is_strict_and_does_not_claim(monkeypatch):
    import openqms_agent_sdk as sdk
    assert hasattr(sdk,'ManagedLaunch'), 'managed SDK cannot attach a platform-owned claim'
    from openqms_agent_sdk import client
    from test_client import FakeTransport
    monkeypatch.setattr(client,'Transport',FakeTransport)
    launch=sdk.ManagedLaunch.from_dict(launch_wire())
    with sdk.RunClient.from_launch(launch) as run:
        assert run.claim.run_id==UUID(int=2)
        assert run._parent._transport.calls==[]
        assert 'synthetic-opaque-token' not in repr(launch)+repr(run)
        wire=run._parent._transport
    assert wire.closed
    for changes in ({'protocol':'unknown'}, {'profile':'model_d5_proposal_v1'}, {'run_id':'bad'},
                    {'lease_epoch':True}, {'lease_expires_at':'2000-01-01T00:00:00Z'}, {'token':'secret\nheader'}):
        with pytest.raises(sdk.SDKError) as caught:
            sdk.ManagedLaunch.from_dict(launch_wire()|changes)
        assert 'synthetic-opaque-token' not in str(caught.value)
    missing=launch_wire(); missing.pop('run_id')
    with pytest.raises(sdk.SDKError): sdk.ManagedLaunch.from_dict(missing)


@pytest.mark.parametrize('operation',['model_turn','model_tool','save_d4_checkpoint','save_d4_candidate'])
def test_new_runtime_client_methods_make_one_narrow_exchange(monkeypatch,operation):
    from test_client import make_client
    from codec_fixtures import U,V
    parent,wire=make_client(monkeypatch)
    run=parent.claim_run(request_key='claim')
    binding=dict(run_id=str(run.claim.run_id),task_id=str(run.claim.task_id))
    wire.responses.update(model_turn=dict(content='hypothesis',tool_calls=[{'id':'opaque','name':'read_inputs'}]),
        model_tool=dict(status='prepared'), save_d4_checkpoint=dict(binding,checkpoint_id=str(U),lease_epoch=1,command_watermark=0),
        save_d4_candidate=dict(binding,candidate_id=str(U),command_id=str(V),report_id=str(U),state='pending',version=1))
    wire.calls.clear()
    if operation=='model_turn': result=run.model_turn(turn=0)
    elif operation=='model_tool': result=run.model_tool(call_id='opaque')
    elif operation=='save_d4_checkpoint': result=run.save_d4_checkpoint()
    else: result=run.save_d4_candidate(command_key='safe',text='hypothesis')
    assert len(wire.calls)==1 and wire.calls[0][0]==operation
    parent.close()
