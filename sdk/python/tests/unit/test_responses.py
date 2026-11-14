import copy
from datetime import timezone
import pytest
from codec_fixtures import codec, decode, deny_network, response_cases, U, V, SECRET
from openqms_agent_sdk import models
from openqms_agent_sdk.errors import ProtocolError


TYPES = dict(zip(models.SUPPORTED_OPERATIONS, (models.ClaimEnvelope,models.Capabilities,models.MessageBatch,models.MessageAck,models.CapaContext,models.RuntimeEvent,models.RuntimeResult,models.ReadonlyCheckpoint,models.MessageHistory,models.FinishResult)))


@pytest.mark.parametrize('op',models.SUPPORTED_OPERATIONS)
def test_all_operation_controls(op):
    result=decode(op,response_cases()[op])
    assert type(result) is TYPES[op]
    assert SECRET not in repr(result)
    assert not hasattr(result,'__dict__')
    if op == 'claim':
        assert result.token == SECRET
        assert not hasattr(result.claim,'token')
        assert result.claim.lease_expires_at.tzinfo is timezone.utc
    if op == 'capa_context':
        assert result.verifications is None
        assert result.updated_at.tzinfo is timezone.utc
    if op == 'message_history':
        assert result.next_sequence == 3 and result.complete is True


def add_unknown(value):
    if type(value) is dict:
        return {**{k:add_unknown(v) for k,v in value.items()},'secret_unknown':SECRET}
    if type(value) is list:
        return [add_unknown(v) for v in value]
    return value


@pytest.mark.parametrize('op',models.SUPPORTED_OPERATIONS)
def test_unknown_additive_fields_discarded_recursively(op):
    value=response_cases()[op]
    assert decode(op,add_unknown(value)) == decode(op,value)


@pytest.mark.parametrize('raw,kind',[
    (b'\xff','invalid_utf8'),(b'{','invalid_json'),(b'[]','schema'),(b'null','schema'),
    (b'{"capabilities":[],"capabilities":[]}','duplicate_key'),
    (b'{"unknown":{"x":1,"x":2}}','duplicate_key'),
    (b'{"x":NaN}','invalid_json'),(b'{"x":Infinity}','invalid_json'),(b'{"x":-Infinity}','invalid_json'),
    (b'{"x":1e999,"capabilities":[]}','invalid_json'),
    pytest.param(b'{"x":'+b'9'*5000+b',"capabilities":[]}', 'invalid_json',id='oversized-integer'),
])
def test_strict_json_no_raw_exception_context(raw,kind):
    with pytest.raises(ProtocolError) as caught:
        codec().decode_response('capabilities',raw)
    assert caught.value.kind == kind
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert not hasattr(caught.value,'original')


def mutate(op,path,value):
    data=copy.deepcopy(response_cases()[op])
    node=data
    for key in path[:-1]: node=node[key]
    node[path[-1]]=value
    return data


@pytest.mark.parametrize('op,path,value',[
    ('claim',('run_id',),SECRET),('claim',('token',),123),
    ('claim',('lease_epoch',),True),('claim',('lease_epoch',),-1),
    ('claim',('lease_expires_at',),'2026-11-03T22:00:00'),
    ('claim',('has_resume_checkpoint',),1),('claim',('accepted_message_seq',),-1),
    ('capabilities',('capabilities',0,'allowed'),1),('capabilities',('capabilities',0,'required'),'false'),
    ('capabilities',('capabilities',0,'projection'),'secret'),
    ('claim_messages',('batch_id',),SECRET),('claim_messages',('messages',0,'sequence'),True),
    ('claim_messages',('messages',0,'content'),42),('claim_messages',('accepted_sequence',),-1),
    ('ack_messages',('accepted_sequence',),True),
    ('capa_context',('projection_id',),'future.raw.v1'),('capa_context',('data_class',),'restricted'),
    ('capa_context',('projection_digest',),'A'*64),('capa_context',('projection_digest',),'a'*63),
    ('capa_context',('factory_id',),SECRET),('capa_context',('updated_at',),'yesterday'),
    ('capa_context',('document_no',),'x'*51),('capa_context',('status',),'x'*21),
    ('record_event',('event_type',),'unknown'),('record_event',('payload','completed'),True),
    ('record_event',('payload','message'),'x'*1001),('record_event',('sources',0,'data_class'),'restricted'),
    ('record_event',('sources',0,'projection_digest'),'z'*64),
    ('save_result',('data_class',),'internal'),('save_result',('payload','explanations'),['x']*21),
    ('save_result',('sources',),[]),('save_checkpoint',('sources',),[]),
    ('save_checkpoint',('update_sequence',),0),('save_checkpoint',('tenant_generation',),False),
    ('save_checkpoint',('created_at',),'2026-11-03'),
    ('message_history',('next_sequence',),True),('message_history',('complete',),1),
    ('finish',('lease_epoch',),-1),('finish',('task_status',),'paused'),
])
def test_schema_negative_controls(op,path,value):
    with pytest.raises(ProtocolError) as caught:
        decode(op,mutate(op,path,value))
    assert caught.value.__context__ is None
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize('op',('record_event','save_result','save_checkpoint','finish'))
@pytest.mark.parametrize('field',('run_id','task_id'))
def test_binding_mismatch(op,field):
    with pytest.raises(ProtocolError) as caught:
        decode(op,mutate(op,(field,),str(V if field=='run_id' else U)))
    assert caught.value.kind == 'binding'


def test_context_source_binding():
    with pytest.raises(ProtocolError) as caught:
        decode('capa_context',mutate('capa_context',('source_capa_id',),str(U)))
    assert caught.value.kind == 'binding'


def test_finish_status_binding():
    data=response_cases()['finish']
    data['task_status']=data['run_status']='failed'
    with pytest.raises(ProtocolError) as caught: decode('finish',data)
    assert caught.value.kind == 'binding'
    assert decode('finish',data,finish_status='failed').run_status == 'failed'


def test_verifications_view_requires_children():
    data=response_cases()['capa_context']
    with pytest.raises(ProtocolError): decode('capa_context',data,view='verifications')
    data['verifications']=[dict(verification_id=str(U),conclusion='passed',is_verified=True,unknown=SECRET)]
    result=decode('capa_context',data,view='verifications')
    assert result.verifications == (models.Verification(U,'passed',True),)
    data['verifications'][0]['is_verified']=1
    with pytest.raises(ProtocolError): decode('capa_context',data,view='verifications')


@pytest.mark.parametrize('op',models.SUPPORTED_OPERATIONS)
def test_required_response_field_missing(op):
    data=response_cases()[op]
    del data[next(iter(data))]
    with pytest.raises(ProtocolError): decode(op,data)


@pytest.mark.parametrize('requested',(None,V,str(V)))
def test_explicit_report_binding_positive(requested):
    assert decode('capa_context',response_cases()['capa_context'],report_id=requested).report_id == V


def test_explicit_report_binding_negative():
    with pytest.raises(ProtocolError) as caught:
        decode('capa_context',response_cases()['capa_context'],report_id=U)
    assert caught.value.kind == 'binding'


@pytest.mark.parametrize('op',('claim_messages','message_history','record_event','save_result','save_checkpoint'))
def test_response_array_bounds(op):
    data=response_cases()[op]
    name='messages' if op in ('claim_messages','message_history') else 'sources'
    item=response_cases()['claim_messages']['messages'][0] if name=='messages' else data[name][0]
    data[name]=[item]*21
    with pytest.raises(ProtocolError): decode(op,data)


def test_empty_batch_and_report_children_semantics():
    assert decode('claim_messages',dict(batch_id=None,messages=[],accepted_sequence=0)).batch_id is None
    data=response_cases()['capa_context']
    data['verifications']=[]
    assert decode('capa_context',data,view='verifications').verifications == ()
    assert decode('capa_context',data).projection_digest == 'a'*64
    assert decode('capa_context',data).verifications is None


@pytest.mark.parametrize('children',[
    [dict(verification_id=str(U),conclusion='passed',is_verified=True,unknown=SECRET)],
    [], None, SECRET, {'secret':SECRET}, [dict(secret=SECRET)],
])
def test_report_drops_additive_children_without_reading_them(children):
    data=response_cases()['capa_context']
    expected=decode('capa_context',data)
    data['verifications']=children
    result=decode('capa_context',data,view='report')
    assert result.verifications is None
    assert result == expected
    assert SECRET not in repr(result)


@pytest.mark.parametrize('children',(None,SECRET,{'secret':SECRET},[dict(secret=SECRET)]))
def test_verifications_view_still_strictly_validates_children(children):
    data=response_cases()['capa_context']
    data['verifications']=children
    with pytest.raises(ProtocolError) as caught:
        decode('capa_context',data,view='verifications')
    assert caught.value.kind == 'schema'


@pytest.mark.parametrize('children,kind',[
    (b'[{"x":1,"x":2}]','duplicate_key'),
    (b'[NaN]','invalid_json'),
])
def test_report_additive_children_still_obey_global_json_rules(children,kind):
    import json
    data=response_cases()['capa_context']
    raw=json.dumps(data).encode()[:-1]+b',"verifications":'+children+b'}'
    with pytest.raises(ProtocolError) as caught:
        codec().decode_response('capa_context',raw,view='report')
    assert caught.value.kind == kind


@pytest.mark.parametrize('value',(None,False,1,[],b'{}'))
def test_only_bytes_response_body(value):
    if value == b'{}':
        value = '{}'
    with pytest.raises(ProtocolError): codec().decode_response('capabilities',value)


def test_isolated_surrogate_response_rejected():
    with pytest.raises(ProtocolError):
        codec().decode_response('claim_messages',b'{"batch_id":null,"messages":[{"message_id":"11111111-1111-4111-8111-111111111111","sequence":1,"content":"\\ud800"}],"accepted_sequence":0}')


def test_timestamps_normalized_and_receipts_not_reordered():
    result=decode('claim',response_cases()['claim'])
    assert result.claim.lease_expires_at.isoformat() == '2026-11-03T14:00:00+00:00'
    data=response_cases()['save_result']
    first=copy.deepcopy(data['sources'][0])
    second=dict(first,receipt_id=str(V))
    data['sources']=[second,first,second]
    assert tuple(item.receipt_id for item in decode('save_result',data).sources) == (V,U,V)


def test_payload_defaults_are_schema_defaults_not_extra_storage():
    data=response_cases()['record_event']
    data['payload']={'future':SECRET}
    assert decode('record_event',data).payload == models.EventPayload()
    data=response_cases()['save_result']
    data['payload']={'future':SECRET}
    assert decode('save_result',data).payload == models.ResultPayload()


@pytest.mark.parametrize('value',(False,0,'1',1.0))
def test_verification_boolean_strict(value):
    data=response_cases()['capa_context']
    data['verifications']=[dict(verification_id=str(U),conclusion='passed',is_verified=value)]
    if value is False:
        assert decode('capa_context',data,view='verifications').verifications[0].is_verified is False
    else:
        with pytest.raises(ProtocolError): decode('capa_context',data,view='verifications')


@pytest.mark.parametrize('raw',(b'{"capabilities":[],"unknown":1} trailing', b'\xef\xbb\xbf{}', b'{"capabilities":[],"unknown":"\\x01"}', b'{'*2000))
def test_json_grammar_and_depth_rejected(raw):
    with pytest.raises(ProtocolError) as caught: codec().decode_response('capabilities',raw)
    assert caught.value.kind == 'invalid_json'
    assert caught.value.__context__ is None
