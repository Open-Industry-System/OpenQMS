"""Strict network-free codec. Unknown response fields never enter DTOs."""
import json
import math
import re
from datetime import datetime, timezone
from uuid import UUID

from . import models
from .errors import ProtocolError, ValidationError


class _Invalid(Exception):
    def __init__(self, kind='schema'):
        self.kind = kind


def _require(condition, kind='schema'):
    if not condition:
        raise _Invalid(kind)


def _text(value, minimum=0, maximum=None):
    _require(type(value) is str, 'invalid_type')
    _require(len(value) >= minimum and (maximum is None or len(value) <= maximum), 'invalid_value')
    _require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), 'invalid_value')
    return value


def _integer(value, minimum=0, maximum=None):
    _require(type(value) is int, 'invalid_type')
    _require(value >= minimum and (maximum is None or value <= maximum), 'invalid_value')
    return value


def _enum(value, choices):
    _text(value)
    _require(value in choices, 'invalid_value')
    return value


def _uuid(value):
    if type(value) is UUID:
        return value
    _require(type(value) is str, 'invalid_uuid')
    invalid = False
    try:
        result = UUID(value)
    except (ValueError, AttributeError, TypeError):
        invalid = True
    if invalid:
        raise _Invalid('invalid_uuid') from None
    return result


def _array(value, minimum=0, maximum=None, *, request=False):
    _require(type(value) in ((list, tuple) if request else (list,)), 'invalid_type')
    _require(len(value) >= minimum and (maximum is None or len(value) <= maximum), 'invalid_value')
    return value


def _event_payload(value, *, request=False):
    if request:
        _require(type(value) is models.EventPayload, 'invalid_type')
        value = {name: getattr(value, name) for name in ('stage','message','completed','total')}
    _require(type(value) is dict, 'invalid_type')
    result = {}
    for name, maximum in (('stage',100),('message',1000),('completed',1000000),('total',1000000)):
        item = value.get(name)
        if item is not None:
            item = _text(item,1,maximum) if name in ('stage','message') else _integer(item,0,maximum)
        result[name] = item
    return result


_RESULT_FIELDS = ('explanations','support','opposition','missing_information','conditional_recommendations')


def _result_payload(value, *, request=False):
    if request:
        _require(type(value) is models.ResultPayload, 'invalid_type')
        value = {name: getattr(value, name) for name in _RESULT_FIELDS}
    _require(type(value) is dict, 'invalid_type')
    result = {}
    for name in _RESULT_FIELDS:
        items = value.get(name, () if request else [])
        if request:
            _require(type(items) is tuple, 'invalid_type')
        result[name] = [_text(item,1,2000) for item in _array(items,0,20,request=request)]
    return result


_REQUEST_FIELDS = {
    'claim': ({'installation_id','secret','request_key'}, {'installation_id','secret','request_key'}),
    'capabilities': (set(),set()),
    'claim_messages': ({'limit'},set()),
    'ack_messages': ({'batch_id','through_sequence'},{'batch_id','through_sequence'}),
    'capa_context': ({'report_id','view'},set()),
    'record_event': ({'idempotency_key','event_type','payload','receipt_ids'},{'idempotency_key','event_type','payload'}),
    'save_result': ({'idempotency_key','payload','receipt_ids'},{'idempotency_key','payload','receipt_ids'}),
    'save_checkpoint': ({'idempotency_key','receipt_ids'},{'idempotency_key','receipt_ids'}),
    'message_history': ({'after_sequence','limit'},set()),
    'finish': ({'status'},{'status'}),
}


def _encode(operation, parameters):
    _require(type(operation) is str and operation in models.SUPPORTED_OPERATIONS, 'invalid_request')
    _require(type(parameters) is dict, 'invalid_request')
    allowed, required = _REQUEST_FIELDS[operation]
    _require(required <= parameters.keys() and parameters.keys() <= allowed, 'invalid_request')
    p = parameters
    if operation == 'capabilities':
        return models.EncodedRequest(None, ())
    if operation == 'capa_context':
        query = []
        if p.get('report_id') is not None:
            query.append(('report_id', str(_uuid(p['report_id']))))
        query.append(('view', _enum(p.get('view','report'), ('report','verifications'))))
        return models.EncodedRequest(None, tuple(query))
    if operation == 'message_history':
        return models.EncodedRequest(None, (
            ('after_sequence',str(_integer(p.get('after_sequence',0),0,2**63-1))),
            ('limit',str(_integer(p.get('limit',20),1,20))),
        ))
    if operation == 'claim':
        body = dict(installation_id=str(_uuid(p['installation_id'])), secret=_text(p['secret'],20,200), request_key=_text(p['request_key'],1,100))
    elif operation == 'claim_messages':
        body = dict(limit=_integer(p.get('limit',20),1,20))
    elif operation == 'ack_messages':
        body = dict(batch_id=str(_uuid(p['batch_id'])), through_sequence=_integer(p['through_sequence'],1))
    elif operation == 'finish':
        body = dict(status=_enum(p['status'],('completed','failed')))
    else:
        body = dict(idempotency_key=_text(p['idempotency_key'],1,100))
        if operation == 'record_event':
            body['event_type'] = _enum(p['event_type'],('progress','query_completed'))
            body['payload'] = _event_payload(p['payload'],request=True)
            minimum = 1 if body['event_type'] == 'query_completed' else 0
        elif operation == 'save_result':
            body['payload'] = _result_payload(p['payload'],request=True)
            minimum = 1
        else:
            minimum = 1
        body['receipt_ids'] = [str(_uuid(item)) for item in _array(p.get('receipt_ids',()),minimum,20,request=True)]
    encoded = json.dumps(body,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    _require(len(encoded) <= models.REQUEST_BUDGET, 'request_too_large')
    return models.EncodedRequest(encoded, ())


def encode_request(operation, parameters):
    """Validate a closed request whitelist before producing transport bytes."""
    kind = None
    try:
        return _encode(operation, parameters)
    except _Invalid as error:
        kind = error.kind
    except (ValueError, TypeError, OverflowError, RecursionError):
        kind = 'invalid_request'
    # Outside except: __context__ must not retain parser exceptions or input.
    raise ValidationError(operation, kind=kind) from None


def _object(value):
    _require(type(value) is dict)
    return value


def _boolean(value):
    _require(type(value) is bool)
    return value


def _timestamp(value):
    _text(value)
    result = datetime.fromisoformat(value)
    _require(result.tzinfo is not None and result.utcoffset() is not None)
    return result.astimezone(timezone.utc)


def _digest(value):
    _text(value)
    _require(re.fullmatch('[a-f0-9]{64}', value) is not None)
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'duplicate_key')
        result[key] = value
    return result


def _constant(value):
    raise _Invalid('invalid_json')


def _float(value):
    result = float(value)
    _require(math.isfinite(result), 'invalid_json')
    return result


def _parse(body):
    _require(type(body) is bytes)
    text = body.decode('utf-8', errors='strict')
    invalid = False
    try:
        result = json.loads(text,object_pairs_hook=_pairs,parse_constant=_constant,parse_float=_float)
    except (ValueError, RecursionError):
        invalid = True
    if invalid:
        raise _Invalid('invalid_json') from None
    return _object(result)


def _message(value):
    p = _object(value)
    return models.RuntimeMessage(_uuid(p['message_id']),_integer(p['sequence'],1),_text(p['content']))


def _source(value):
    p = _object(value)
    return models.Source(
        _uuid(p['receipt_id']), _uuid(p['source_capa_id']),
        _enum(p['projection_id'],('capa.d4.summary.masked.v1',)),
        _digest(p['projection_digest']), _enum(p['data_class'],('internal',)),
    )


def _sources(value, minimum):
    return tuple(_source(item) for item in _array(value,minimum,20))


def _verification(value):
    p = _object(value)
    return models.Verification(_uuid(p['verification_id']),_enum(p['conclusion'],('pending','passed','failed')),_boolean(p['is_verified']))


def _context(p, view, requested_report_id):
    _enum(view,('report','verifications'))
    report_id = _uuid(p['report_id'])
    source_id = _uuid(p['source_capa_id'])
    _require(source_id == report_id, 'binding')
    if requested_report_id is not None:
        _require(report_id == _uuid(requested_report_id), 'binding')
    children = None
    if view == 'verifications':
        children = tuple(_verification(item) for item in _array(p['verifications']))
    return models.CapaContext(
        receipt_id=_uuid(p['receipt_id']),source_capa_id=source_id,report_id=report_id,
        factory_id=_uuid(p['factory_id']),
        projection_id=_enum(p['projection_id'],('capa.d4.summary.masked.v1',)),
        data_class=_enum(p['data_class'],('internal',)),
        document_no=_text(p['document_no'],0,50),status=_text(p['status'],0,20),
        severity=_text(p['severity'],0,20),product_line_code=_text(p['product_line_code'],0,20),
        updated_at=_timestamp(p['updated_at']),projection_digest=_digest(p['projection_digest']),
        verifications=children,
    )


def _decode(operation, p, *, view, run_id, task_id, finish_status, report_id):
    _require(type(operation) is str and operation in models.SUPPORTED_OPERATIONS)
    if operation == 'claim':
        claim = models.RunClaim(
            _uuid(p['run_id']),_uuid(p['task_id']),_integer(p['lease_epoch']),
            _timestamp(p['lease_expires_at']),_integer(p['accepted_message_seq']),_boolean(p['has_resume_checkpoint']),
        )
        return models.ClaimEnvelope(claim,_text(p['token'],1))
    if operation == 'capabilities':
        capabilities = []
        for item in _array(p['capabilities']):
            item = _object(item)
            projection = item['projection']
            if projection is not None:
                projection = _enum(projection,('masked','raw'))
            capabilities.append(models.Capability(_text(item['id']),_boolean(item['allowed']),_boolean(item['required']),projection))
        return models.Capabilities(tuple(capabilities))
    if operation == 'claim_messages':
        batch_id = p['batch_id']
        return models.MessageBatch(None if batch_id is None else _uuid(batch_id),tuple(_message(item) for item in _array(p['messages'],0,20)),_integer(p['accepted_sequence']))
    if operation == 'ack_messages':
        return models.MessageAck(_integer(p['accepted_sequence']))
    if operation == 'message_history':
        return models.MessageHistory(tuple(_message(item) for item in _array(p['messages'],0,20)),_integer(p['next_sequence']),_boolean(p['complete']))
    if operation == 'capa_context':
        return _context(p, view, report_id)
    actual_run, actual_task = _uuid(p['run_id']), _uuid(p['task_id'])
    if run_id is not None:
        _require(actual_run == _uuid(run_id), 'binding')
    if task_id is not None:
        _require(actual_task == _uuid(task_id), 'binding')
    binding = dict(run_id=actual_run,task_id=actual_task)
    if operation == 'record_event':
        event_type = _enum(p['event_type'],('progress','query_completed'))
        sources = _sources(p['sources'],1 if event_type == 'query_completed' else 0)
        return models.RuntimeEvent(event_id=_uuid(p['event_id']),**binding,event_type=event_type,payload=models.EventPayload(**_event_payload(p['payload'])),sources=sources)
    if operation == 'save_result':
        payload = {name:tuple(items) for name,items in _result_payload(p['payload']).items()}
        return models.RuntimeResult(result_id=_uuid(p['result_id']),**binding,data_class=_enum(p['data_class'],('restricted',)),payload=models.ResultPayload(**payload),sources=_sources(p['sources'],1))
    if operation == 'save_checkpoint':
        return models.ReadonlyCheckpoint(
            checkpoint_id=_uuid(p['checkpoint_id']),**binding,lease_epoch=_integer(p['lease_epoch']),
            tenant_generation=_integer(p['tenant_generation']),accepted_message_seq=_integer(p['accepted_message_seq']),
            update_sequence=_integer(p['update_sequence'],1),created_at=_timestamp(p['created_at']),sources=_sources(p['sources'],1),
        )
    task_status = _enum(p['task_status'],('blocked_capability','ready','paused','completed','failed','cancelled'))
    run_status = _enum(p['run_status'],('pending','active','paused','stopped','completed','failed'))
    if finish_status is not None:
        _enum(finish_status,('completed','failed'))
        _require(task_status == run_status == finish_status, 'binding')
    return models.FinishResult(**binding,task_status=task_status,run_status=run_status,lease_epoch=_integer(p['lease_epoch']))


def decode_response(operation, body, *, view='report', run_id=None, task_id=None, finish_status=None, report_id=None):
    """Strictly parse JSON, then project only known validated DTO fields.

    The final epoch is informational, never a renewed credential. A history
    cursor may return the server's waterline below the requested cursor.
    """
    kind = None
    try:
        return _decode(operation,_parse(body),view=view,run_id=run_id,task_id=task_id,finish_status=finish_status,report_id=report_id)
    except UnicodeDecodeError:
        kind = 'invalid_utf8'
    except (json.JSONDecodeError, RecursionError):
        kind = 'invalid_json'
    except _Invalid as error:
        kind = error.kind if error.kind in ('duplicate_key','invalid_json','binding') else 'schema'
    except (KeyError, ValueError, TypeError, OverflowError):
        kind = 'schema'
    raise ProtocolError(operation, kind=kind) from None
