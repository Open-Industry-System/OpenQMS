import json
import pytest
from codec_fixtures import codec, deny_network, U, V, SECRET
from openqms_agent_sdk import models
from openqms_agent_sdk.errors import ValidationError


def cases():
    return [
        ('claim', dict(installation_id=U, secret=SECRET, request_key='k'), dict(installation_id=str(U), secret=SECRET, request_key='k')),
        ('claim_messages', {}, {'limit':20}),
        ('ack_messages', dict(batch_id=U, through_sequence=1), dict(batch_id=str(U), through_sequence=1)),
        ('record_event', dict(idempotency_key='k', event_type='progress', payload=models.EventPayload(completed=2,total=1)), dict(idempotency_key='k',event_type='progress',payload=dict(stage=None,message=None,completed=2,total=1),receipt_ids=[])),
        ('save_result', dict(idempotency_key='k',payload=models.ResultPayload(explanations=('中文',)),receipt_ids=(V,U,V)), dict(idempotency_key='k',payload=dict(explanations=['中文'],support=[],opposition=[],missing_information=[],conditional_recommendations=[]),receipt_ids=[str(V),str(U),str(V)])),
        ('save_checkpoint',dict(idempotency_key='k',receipt_ids=(U,)),dict(idempotency_key='k',receipt_ids=[str(U)])),
        ('finish',dict(status='completed'),dict(status='completed')),
    ]


@pytest.mark.parametrize('op,params,expected', cases())
def test_body_controls(op, params, expected):
    result = codec().encode_request(op, params)
    assert json.loads(result.body) == expected
    assert result.query == ()
    assert SECRET not in repr(result)
    assert b'\\u4e2d' not in result.body
    assert result.body == json.dumps(expected,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()


@pytest.mark.parametrize('op,params,query', [
    ('capabilities',{},()),
    ('capa_context',{},(('view','report'),)),
    ('capa_context',{'report_id':None,'view':'verifications'},(('view','verifications'),)),
    ('capa_context',{'report_id':U},(('report_id',str(U)),('view','report'))),
    ('message_history',{},(('after_sequence','0'),('limit','20'))),
    ('message_history',{'after_sequence':2**63-1,'limit':1},(('after_sequence',str(2**63-1)),('limit','1'))),
])
def test_query_controls(op,params,query):
    result=codec().encode_request(op,params)
    assert result.body is None
    assert result.query == query


@pytest.mark.parametrize('op,params', [
    ('claim',dict(installation_id=object(),secret=SECRET,request_key='k')),
    ('claim',dict(installation_id=U,secret='x'*19,request_key='k')),
    ('claim',dict(installation_id=U,secret='x'*201,request_key='k')),
    ('claim',dict(installation_id=U,secret=SECRET,request_key='')),
    ('claim_messages',{'limit':True}),('claim_messages',{'limit':0}),('claim_messages',{'limit':21}),('claim_messages',{'limit':None}),
    ('ack_messages',{'batch_id':U,'through_sequence':0}),
    ('capa_context',{'view':'raw'}),('capa_context',{'report_id':False}),
    ('record_event',dict(idempotency_key='k',event_type='query_completed',payload=models.EventPayload())),
    ('record_event',dict(idempotency_key='k',event_type='progress',payload=models.EventPayload(completed=True))),
    ('record_event',dict(idempotency_key='k',event_type='progress',payload=models.EventPayload(stage=''))),
    ('record_event',dict(idempotency_key='k',event_type='progress',payload=models.EventPayload(message='x'*1001))),
    ('record_event',dict(idempotency_key='k',event_type='progress',payload=models.EventPayload(total=1000001))),
    ('save_result',dict(idempotency_key='k',receipt_ids=(U,),payload=models.ResultPayload(support=('x',)*21))),
    ('save_result',dict(idempotency_key='k',receipt_ids=(U,),payload=models.ResultPayload(support=('x'*2001,)))),
    ('save_result',dict(idempotency_key='k',receipt_ids=(),payload=models.ResultPayload())),
    ('save_checkpoint',dict(idempotency_key='k',receipt_ids=(U,),state={})),
    ('save_checkpoint',dict(idempotency_key='k',receipt_ids=(U,)*21)),
    ('message_history',{'after_sequence':2**63}),('message_history',{'after_sequence':True}),
    ('message_history',{'after_sequence':'01'}),('message_history',{'limit':0}),
    ('finish',{'status':'paused'}),('capabilities',{'secret':SECRET}),
])
def test_rejects_invalid_request(op,params):
    with pytest.raises(ValidationError) as caught:
        codec().encode_request(op,params)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert SECRET not in repr(caught.value)


@pytest.mark.parametrize('op,params,_',cases())
def test_every_body_operation_rejects_unknown_fields(op,params,_):
    with pytest.raises(ValidationError):
        codec().encode_request(op,dict(params,unknown=SECRET))


def test_size_budget_is_utf8_bytes():
    params=dict(idempotency_key='k',receipt_ids=(U,),payload=models.ResultPayload(**{name:('\U0001f600'*2000,)*20 for name in models.ResultPayload.__dataclass_fields__}))
    # Shrink the shared budget to exercise the pre-transport defense with legal fields.
    from unittest.mock import patch
    with patch.object(models,'REQUEST_BUDGET',100):
        with pytest.raises(ValidationError) as caught:
            codec().encode_request('save_result',params)
    assert caught.value.kind == 'request_too_large'


def test_uuid_raw_failure_has_no_context():
    with pytest.raises(ValidationError) as caught:
        codec().encode_request('claim',dict(installation_id=SECRET,secret=SECRET,request_key='k'))
    assert caught.value.kind == 'invalid_uuid'
    assert caught.value.__context__ is None
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize('op,params',[
    ('claim',dict(installation_id=str(U),secret='x'*20,request_key='k')),
    ('claim',dict(installation_id=U,secret='x'*200,request_key='k'*100)),
    ('claim_messages',dict(limit=1)),('claim_messages',dict(limit=20)),
    ('ack_messages',dict(batch_id=str(U),through_sequence=2**63)),
    ('record_event',dict(idempotency_key='k'*100,event_type='progress',payload=models.EventPayload(stage='s'*100,message='m'*1000,completed=0,total=1000000),receipt_ids=(U,)*20)),
    ('record_event',dict(idempotency_key='k',event_type='query_completed',payload=models.EventPayload(),receipt_ids=(U,))),
    ('save_result',dict(idempotency_key='k',receipt_ids=(U,)*20,payload=models.ResultPayload(**{name:('x'*2000,)*20 for name in models.ResultPayload.__dataclass_fields__}))),
    ('save_checkpoint',dict(idempotency_key='k'*100,receipt_ids=(str(U),)*20)),
    ('finish',dict(status='failed')),
])
def test_exact_request_boundaries_accepted(op,params):
    assert codec().encode_request(op,params).body is not None


@pytest.mark.parametrize('op',models.SUPPORTED_OPERATIONS)
def test_unknown_top_level_fields_fail_before_missing_fields(op):
    with pytest.raises(ValidationError) as caught:
        codec().encode_request(op,dict(unknown=SECRET))
    assert caught.value.kind == 'invalid_request'


@pytest.mark.parametrize('name',models.ResultPayload.__dataclass_fields__)
@pytest.mark.parametrize('items',([SECRET],('',),('x'*2001,), (1,), None))
def test_result_tuple_text_strictness(name,items):
    with pytest.raises(ValidationError):
        codec().encode_request('save_result',dict(idempotency_key='k',receipt_ids=(U,),payload=models.ResultPayload(**{name:items})))


@pytest.mark.parametrize('op,params',[
    ('claim',dict(installation_id=U,secret=None,request_key='k')),
    ('claim',dict(installation_id=U,secret=SECRET,request_key=1)),
    ('record_event',dict(idempotency_key='k',event_type='progress',payload=None)),
    ('record_event',dict(idempotency_key='k',event_type='progress',payload={})),
    ('record_event',dict(idempotency_key='k',event_type='progress',payload=models.EventPayload(),receipt_ids=None)),
    ('save_checkpoint',dict(idempotency_key='k',receipt_ids=(U,),epoch=0)),
    ('save_checkpoint',dict(idempotency_key='k',receipt_ids=(U,),cursor=0)),
    ('save_checkpoint',dict(idempotency_key='k',receipt_ids=())),
    ('capa_context',dict(view=None)),('message_history',dict(limit=None)),
    ('message_history',dict(after_sequence=-1)),('message_history',dict(limit=21)),
])
def test_none_coercion_and_forbidden_fields(op,params):
    with pytest.raises(ValidationError): codec().encode_request(op,params)


def test_never_stringifies_arbitrary_input():
    class Trap:
        def __str__(self):
            raise AssertionError('arbitrary __str__ executed')
    with pytest.raises(ValidationError):
        codec().encode_request('claim',dict(installation_id=Trap(),secret=SECRET,request_key='k'))


def test_budget_includes_exact_utf8_boundary(monkeypatch):
    params=dict(installation_id=U,secret=SECRET,request_key='中文')
    body=codec().encode_request('claim',params).body
    monkeypatch.setattr(models,'REQUEST_BUDGET',len(body))
    assert codec().encode_request('claim',params).body == body
    monkeypatch.setattr(models,'REQUEST_BUDGET',len(body)-1)
    with pytest.raises(ValidationError) as caught: codec().encode_request('claim',params)
    assert caught.value.kind == 'request_too_large'
