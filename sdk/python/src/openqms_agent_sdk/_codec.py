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
    'model_turn': ({'turn'},set()),
    'model_tool': ({'call_id'},{'call_id'}),
    'save_d4_checkpoint': (set(),set()),
    'pfmea_impact_material': (set(), set()),
    'pfmea_impact_search': ({'term', 'cursor'}, {'term'}),
    'pfmea_impact_page': ({'scope_ref', 'cursor'}, {'scope_ref'}),
    'pfmea_impact_confirm': ({'release_id', 'page_key', 'payload_digest', 'token'},
                             {'release_id', 'page_key', 'payload_digest', 'token'}),
    'pfmea_impact_result': ({'operation_key', 'analyses', 'assessments'},
                            {'operation_key', 'analyses', 'assessments'}),
    'save_d4_candidate': ({'command_key','text','supporting','opposing','missing_information','operation','predecessor_id','correction_message_id'}, {'command_key','text'}),
}


def _encode(operation, parameters):
    _require(type(operation) is str and operation in models.SUPPORTED_OPERATIONS, 'invalid_request')
    _require(type(parameters) is dict, 'invalid_request')
    allowed, required = _REQUEST_FIELDS[operation]
    _require(required <= parameters.keys() and parameters.keys() <= allowed, 'invalid_request')
    p = parameters
    if operation in ('capabilities', 'pfmea_impact_material'):
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
    if operation.startswith('pfmea_impact_'):
        from ._pfmea import encode_body
        body = encode_body(operation, p)
    elif operation == 'model_turn':
        body = dict(operation='workflow',turn=_integer(p.get('turn',0),0,8))
    elif operation == 'model_tool':
        body = dict(call_id=_text(p['call_id'],1,100))
    elif operation == 'save_d4_checkpoint':
        body = {}
    elif operation == 'claim':
        body = dict(installation_id=str(_uuid(p['installation_id'])), secret=_text(p['secret'],20,200), request_key=_text(p['request_key'],1,100))
    elif operation == 'claim_messages':
        body = dict(limit=_integer(p.get('limit',20),1,20))
    elif operation == 'ack_messages':
        body = dict(batch_id=str(_uuid(p['batch_id'])), through_sequence=_integer(p['through_sequence'],1))
    elif operation == 'save_d4_candidate':
        key = _text(p['command_key'],1,128)
        _require(re.fullmatch(r'[A-Za-z0-9._:-]+', key) is not None, 'invalid_value')
        text = _text(p['text'],1,16384)
        _require(text.strip() and len(text.encode('utf-8')) <= 16384 and '\x00' not in text, 'invalid_value')
        body = dict(command_key=key, text=text, operation=_enum(p.get('operation','save'),('save','alternative','replace')))
        for name in ('supporting','opposing','missing_information'):
            body[name] = [_text(item,1,2000) for item in _array(p.get(name,()),0,20,request=True)]
            _require(all('\x00' not in item and len(item.encode('utf-8')) <= 2000 for item in body[name]), 'invalid_value')
        predecessor, correction = p.get('predecessor_id'), p.get('correction_message_id')
        _require((body['operation']=='replace') == (predecessor is not None and correction is not None), 'invalid_value')
        _require(body['operation']=='replace' or predecessor is None and correction is None, 'invalid_value')
        if predecessor is not None:
            body.update(predecessor_id=str(_uuid(predecessor)), correction_message_id=str(_uuid(correction)))
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
    if operation == 'pfmea_impact_result':
        from ._pfmea import MAX_BYTES
        # Stop serializing before a large composition of individually valid
        # analysis fields can allocate an oversized request.
        chunks = bytearray()
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        for fragment in encoder.iterencode(body):
            data = fragment.encode('utf-8')
            _require(len(chunks) + len(data) <= MAX_BYTES, 'request_too_large')
            chunks.extend(data)
        encoded = bytes(chunks)
    else:
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


def _decode(operation, p, *, view, run_id, task_id, finish_status, report_id,
            lease_epoch=None, scope_ref=None, snapshot_digest=None):
    _require(type(operation) is str and operation in models.SUPPORTED_OPERATIONS)
    if operation.startswith('pfmea_impact_'):
        from ._pfmea import decode_response
        return decode_response(operation, p, run_id=run_id, task_id=task_id,
            lease_epoch=lease_epoch, scope_ref=scope_ref, snapshot_digest=snapshot_digest)
    if operation == 'model_turn':
        calls=tuple(models.ModelToolCall(_text(item['id'],1,100),_enum(item['name'],('read_inputs','save_candidate','request_supplement'))) for item in _array(p['tool_calls'],0,8))
        _require(len({item.id for item in calls})==len(calls),'schema')
        return models.ModelTurn(_text(p['content'],0,65536),calls)
    if operation == 'model_tool':
        status=_enum(p['status'],('prepared','saved','waiting','accepted'))
        candidate=_uuid(p['candidate_id']) if status=='saved' else None
        sequence=_integer(p['accepted_sequence']) if status=='accepted' else None
        return models.ModelToolResult(status,candidate,sequence)
    if operation == 'save_d4_checkpoint':
        actual_run,actual_task=_uuid(p['run_id']),_uuid(p['task_id'])
        _require(run_id is None or actual_run==_uuid(run_id),'binding')
        _require(task_id is None or actual_task==_uuid(task_id),'binding')
        return models.D4CandidateCheckpoint(_uuid(p['checkpoint_id']),actual_task,actual_run,_integer(p['lease_epoch']),_integer(p['command_watermark']))
    if operation == 'save_d4_candidate':
        actual_run, actual_task = _uuid(p['run_id']), _uuid(p['task_id'])
        _require(run_id is None or actual_run == _uuid(run_id), 'binding')
        _require(task_id is None or actual_task == _uuid(task_id), 'binding')
        return models.D4CandidateReference(_uuid(p['candidate_id']), _uuid(p['command_id']),
            actual_task, actual_run, _uuid(p['report_id']),
            _enum(p['state'],('pending','adopted','withdrawn','superseded')), _integer(p['version'],1))
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


def decode_response(operation, body, *, view='report', run_id=None, task_id=None,
                    finish_status=None, report_id=None, lease_epoch=None, scope_ref=None, snapshot_digest=None):
    """Strictly parse JSON, then project only known validated DTO fields.

    The final epoch is informational, never a renewed credential. A history
    cursor may return the server's waterline below the requested cursor.
    """
    kind = None
    try:
        return _decode(operation, _parse(body), view=view, run_id=run_id, task_id=task_id,
            finish_status=finish_status, report_id=report_id, lease_epoch=lease_epoch,
            scope_ref=scope_ref, snapshot_digest=snapshot_digest)
    except UnicodeDecodeError:
        kind = 'invalid_utf8'
    except (json.JSONDecodeError, RecursionError):
        kind = 'invalid_json'
    except _Invalid as error:
        kind = error.kind if error.kind in ('duplicate_key','invalid_json','binding') else 'schema'
    except (KeyError, ValueError, TypeError, OverflowError):
        kind = 'schema'
    raise ProtocolError(operation, kind=kind) from None


def decode_managed_launch(value):
    """Strict versioned managed envelope; diagnostics never retain its contents."""
    kind=None
    try:
        _require(type(value) is dict,'invalid_type')
        fields={'protocol','profile','api_origin','tenant_slug','token','task_id','run_id','deployment_id',
            'lease_epoch','lease_expires_at','accepted_message_seq','has_resume_checkpoint'}
        _require(set(value)==fields,'invalid_request')
        return models.ManagedLaunch(_text(value['protocol'], 1, 100),
            _text(value['profile'], 1, 100), _text(value['api_origin'],1,2048),
            _text(value['tenant_slug'],1,100), _text(value['token'],1,8192),
            _uuid(value['task_id']),_uuid(value['run_id']),_uuid(value['deployment_id']),
            _integer(value['lease_epoch']),_timestamp(value['lease_expires_at']),
            _integer(value['accepted_message_seq']),_boolean(value['has_resume_checkpoint']))
    except _Invalid as error:
        kind=error.kind
    except (ValueError,TypeError,KeyError,OverflowError):
        kind='invalid_request'
    from .errors import ConfigError
    raise ConfigError('config',kind=kind) from None
