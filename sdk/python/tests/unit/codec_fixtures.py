"""Codec-local fixtures; block all networking before SDK imports."""
import socket
from uuid import UUID

import pytest


def _deny_network(*args, **kwargs):
    raise AssertionError("network forbidden")


def _guard(monkeypatch, denied):
    for name in ('connect','connect_ex','bind'):
        monkeypatch.setattr(socket.socket,name,denied)
    for name in ('create_connection','getaddrinfo','gethostbyname','gethostbyname_ex','gethostbyaddr'):
        monkeypatch.setattr(socket,name,denied)


# Cover collection-time SDK imports, then restore before other modules run.
with pytest.MonkeyPatch.context() as _patch:
    _guard(_patch, _deny_network)
    from openqms_agent_sdk import models


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    attempts = []

    def denied(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('network forbidden')

    _guard(monkeypatch, denied)
    yield
    assert not attempts

U = UUID("11111111-1111-4111-8111-111111111111")
V = UUID("22222222-2222-4222-8222-222222222222")
SECRET = "secret-sentinel-never-disclose"


def codec():
    from openqms_agent_sdk import _codec
    return _codec


def response_cases():
    source = dict(receipt_id=str(U),source_capa_id=str(V),projection_id='capa.d4.summary.masked.v1',projection_digest='a'*64,data_class='internal')
    binding = dict(run_id=str(U),task_id=str(V))
    message = dict(message_id=str(U),sequence=1,content=SECRET)
    context = dict(receipt_id=str(U),source_capa_id=str(V),report_id=str(V),factory_id=str(U),projection_id=source['projection_id'],data_class='internal',document_no=SECRET,status='draft',severity='一般',product_line_code='line',updated_at='2026-11-03T22:00:00+08:00',projection_digest='a'*64)
    return {
        'claim': dict(**binding,token=SECRET,lease_epoch=0,lease_expires_at='2026-11-03T22:00:00+08:00',accepted_message_seq=0,has_resume_checkpoint=False),
        'capabilities': dict(capabilities=[dict(id='future.optional.v1',allowed=True,required=False,projection=None)]),
        'claim_messages': dict(batch_id=str(U),messages=[message],accepted_sequence=0),
        'ack_messages': dict(accepted_sequence=1),
        'capa_context': context,
        'record_event': dict(**binding,event_id=str(U),event_type='progress',payload=dict(message=SECRET,completed=2,total=1),sources=[source]),
        'save_result': dict(**binding,result_id=str(U),data_class='restricted',payload=dict(explanations=[SECRET]),sources=[source]),
        'save_checkpoint': dict(**binding,checkpoint_id=str(U),lease_epoch=0,tenant_generation=0,accepted_message_seq=0,update_sequence=1,created_at='2026-11-03T22:00:00+08:00',sources=[source]),
        'message_history': dict(messages=[],next_sequence=3,complete=True),
        'finish': dict(**binding,task_status='completed',run_status='completed',lease_epoch=1),
    }


def decode(op, value, **kwargs):
    import json
    if op in ('record_event','save_result','save_checkpoint','finish'):
        kwargs = dict(run_id=U,task_id=V,**kwargs)
    if op == 'finish':
        kwargs.setdefault('finish_status','completed')
    return codec().decode_response(op,json.dumps(value,ensure_ascii=False).encode(),**kwargs)
