"""Local, stdlib-only readonly D4 metadata plugin (no model or business commands).

Trusted deployment configuration, all through environment:
OPENQMS_API_BASE_URL       http(s) loopback origin, no path/query/fragment
OPENQMS_INSTALLATION_ID    registered installation UUID
OPENQMS_INSTALLATION_SECRET one-time secret; never printed
OPENQMS_CLAIM_KEY          stable retry key (default readonly-8d-v1)
OPENQMS_TENANT_SLUG        optional trusted development routing configuration
OPENQMS_READONLY_CHECKPOINT off (default) or save: server-position checkpoint
OPENQMS_READONLY_FINISH    off (default) or completed: drain input then finish

No user JWT or initial report selector is accepted. Instructions are acknowledged
in sequence but never executed. Analysis concerns verification metadata only;
it cannot establish root causes, inspect evidence, or change business state.
"""
from datetime import datetime
import hashlib
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID

SUMMARY = 'capa.d4.summary.masked.v1'
MAX_RESPONSE = 1024 * 1024


class PluginError(Exception):
    """Messages must stay constant and content/credential free."""


def require(condition):
    if not condition:
        raise PluginError('Invalid runtime response')


def identifier(value):
    require(isinstance(value, str))
    try:
        require(str(UUID(value)) == value)
    except (ValueError, TypeError, AttributeError):
        raise PluginError('Invalid runtime response') from None
    return value


def local_origin(value):
    try:
        url = urlsplit(value)
        require(url.scheme in {'http', 'https'} and url.hostname in {'127.0.0.1', 'localhost', '::1'}
            and url.username is None and url.password is None and url.path in {'', '/'}
            and not url.query and not url.fragment and '?' not in value and '#' not in value)
        require(url.port is None or 1 <= url.port <= 65535)
    except (ValueError, TypeError):
        raise PluginError('Invalid local configuration') from None
    return value.rstrip('/')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward installation secrets or Bearer credentials, even to a
        # second loopback endpoint. Proxy environment variables are ignored too.
        return None


class Client:
    def __init__(self, origin, tenant_slug=''):
        self.origin = local_origin(origin)
        require(isinstance(tenant_slug, str) and len(tenant_slug) <= 100
            and (not tenant_slug or re.fullmatch(r'[a-z0-9][a-z0-9-]*', tenant_slug)))
        self.headers = {'Accept': 'application/json'}
        if tenant_slug:
            self.headers['X-Tenant-ID'] = tenant_slug
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, method, path, body=None, query=None):
        payload = None if body is None else json.dumps(body, separators=(',', ':')).encode()
        headers = {**self.headers, 'Content-Type': 'application/json'}
        url = self.origin+'/api/agent/runtime'+path
        if query:
            url += '?'+urlencode(query)
        try:
            with self.opener.open(Request(url, data=payload, headers=headers, method=method), timeout=10) as response:
                require(response.status == 200)
                data = response.read(MAX_RESPONSE+1)
                require(len(data) <= MAX_RESPONSE)
                result = json.loads(data)
                require(type(result) is dict)
                return result
        except HTTPError as error:
            error.close()
            # Never include response bodies, URLs, headers, or Python tracebacks.
            raise PluginError('Runtime request rejected') from None
        except (URLError, OSError, ValueError, UnicodeError):
            raise PluginError('Runtime request failed') from None


def projection(body, *, children=False, previous=None):
    keys = {'projection_id', 'source_capa_id', 'data_class', 'report_id', 'document_no', 'status',
        'severity', 'factory_id', 'product_line_code', 'updated_at', 'projection_digest', 'receipt_id'}
    if children:
        keys.add('verifications')
    require(set(body) == keys and body['projection_id'] == SUMMARY and body['data_class'] == 'internal')
    for key in ('receipt_id', 'source_capa_id', 'report_id', 'factory_id'):
        identifier(body[key])
    require(body['source_capa_id'] == body['report_id'])
    for key, limit in (('document_no', 50), ('status', 20), ('severity', 20), ('product_line_code', 20), ('updated_at', 100)):
        require(isinstance(body[key], str) and 0 < len(body[key]) <= limit)
    require(isinstance(body['projection_digest'], str) and re.fullmatch('[a-f0-9]{64}', body['projection_digest']))
    if previous:
        require(all(body[key] == previous[key] for key in keys - {'receipt_id', 'verifications'})
            and body['receipt_id'] != previous['receipt_id'])
    if children:
        require(type(body['verifications']) is list)
        ids = []
        for row in body['verifications']:
            require(type(row) is dict and set(row) == {'verification_id', 'conclusion', 'is_verified'})
            ids.append(identifier(row['verification_id']))
            require(row['conclusion'] in {'pending', 'passed', 'failed'} and type(row['is_verified']) is bool
                and row['is_verified'] == (row['conclusion'] == 'passed'))
        require(ids == sorted(set(ids)))
        canonical = {key: value for key, value in body.items() if key not in {'receipt_id', 'projection_digest'}}
        digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        require(body['projection_digest'] == digest)
    return body


def metadata_analysis(report, children):
    rows = children['verifications']
    counts = {value: sum(row['conclusion'] == value for row in rows) for value in ('passed', 'pending', 'failed')}
    # This decision uses only the returned D4 metadata, never message instructions
    # or root-cause/evidence text. Statements deliberately avoid causal inference.
    return {
        'explanations': [f"D4 verification metadata: {len(rows)} records; {counts['passed']} passed, {counts['pending']} pending, {counts['failed']} failed."],
        'support': [f"{counts['passed']} verification records are marked verified."] if counts['passed'] else [],
        'opposition': [f"{counts['failed']} verification records are marked failed."] if counts['failed'] else [],
        'missing_information': ['Root-cause text and evidence are outside this metadata projection; causal conclusions cannot be established.'],
        'conditional_recommendations': ['If verification remains pending or failed, an authorized employee should review its evidence through the normal business workflow.']
            if counts['pending'] or counts['failed'] or not rows else ['An authorized employee should review evidence before accepting any causal conclusion.']}



def input_page(messages, last, *, allow_empty=False):
    require(type(messages) is list and len(messages) <= 20 and (messages or allow_empty))
    for message in messages:
        require(type(message) is dict and set(message) == {'message_id', 'sequence', 'content'})
        identifier(message['message_id'])
        require(type(message['sequence']) is int and message['sequence'] == last+1
            and isinstance(message['content'], str) and len(message['content']) <= 10000)
        # Restricted original text is consumed as data, never evaluated/printed.
        last = message['sequence']
    return last



def timestamp(value):
    require(isinstance(value, str) and 0 < len(value) <= 100)
    require(datetime.fromisoformat(value).tzinfo is not None)


def checkpoint_response(body, task_id, run_id, epoch, accepted, projections):
    require(set(body) == {'checkpoint_id', 'task_id', 'run_id', 'lease_epoch',
        'tenant_generation', 'accepted_message_seq', 'update_sequence', 'created_at', 'sources'})
    checkpoint_id = identifier(body['checkpoint_id'])
    require(body['task_id'] == task_id and body['run_id'] == run_id
        and type(body['lease_epoch']) is int and body['lease_epoch'] == epoch
        and type(body['accepted_message_seq']) is int and body['accepted_message_seq'] == accepted
        and type(body['tenant_generation']) is int and body['tenant_generation'] >= 0
        and type(body['update_sequence']) is int and body['update_sequence'] > 0)
    timestamp(body['created_at'])
    require(type(body['sources']) is list and len(body['sources']) == 2)
    expected = {p['receipt_id']: {key:p[key] for key in ('receipt_id', 'source_capa_id',
        'projection_id', 'projection_digest', 'data_class')} for p in projections}
    require(all(type(source) is dict and source == expected.get(source.get('receipt_id'))
        for source in body['sources']) and {source['receipt_id'] for source in body['sources']} == set(expected))
    return checkpoint_id

def epoch_key(base, epoch):
    return base if epoch == 1 else base+'-epoch-'+str(epoch)

def run():
    require(len(sys.argv) == 1)  # No arbitrary client-selected target argument.
    checkpoint_mode = os.environ.get('OPENQMS_READONLY_CHECKPOINT', 'off')
    finish_mode = os.environ.get('OPENQMS_READONLY_FINISH', 'off')
    require(checkpoint_mode in {'off', 'save'} and finish_mode in {'off', 'completed'})
    client = Client(os.environ.get('OPENQMS_API_BASE_URL', ''), os.environ.get('OPENQMS_TENANT_SLUG', ''))
    installation = identifier(os.environ.get('OPENQMS_INSTALLATION_ID', ''))
    secret = os.environ.get('OPENQMS_INSTALLATION_SECRET', '')
    key = os.environ.get('OPENQMS_CLAIM_KEY', 'readonly-8d-v1')
    require(20 <= len(secret) <= 200 and 1 <= len(key) <= 100)
    claim = client.request('POST', '/claim', {'installation_id': installation, 'secret': secret, 'request_key': key})
    require(set(claim) == {'run_id', 'task_id', 'token', 'lease_epoch', 'lease_expires_at',
        'accepted_message_seq', 'has_resume_checkpoint'})
    task_id, run_id = identifier(claim['task_id']), identifier(claim['run_id'])
    require(type(claim['accepted_message_seq']) is int and claim['accepted_message_seq'] >= 0
        and type(claim['has_resume_checkpoint']) is bool)
    require(type(claim['lease_epoch']) is int and claim['lease_epoch'] > 0
        and isinstance(claim['token'], str) and 0 < len(claim['token']) <= 10000)
    timestamp(claim['lease_expires_at'])
    client.headers['Authorization'] = 'Bearer '+claim['token']
    # A new epoch/process has no internal plugin memory. Reconstruct only the
    # server-proven accepted input prefix before claiming any new instructions.
    accepted = claim['accepted_message_seq']
    last = 0
    for _ in range(1000):  # bounded total work; every history page is <=20
        if last == accepted:
            break
        history = client.request('GET', '/messages/history',
            query={'after_sequence': last, 'limit': 20})
        require(set(history) == {'messages', 'next_sequence', 'complete'}
            and type(history['complete']) is bool)
        last = input_page(history['messages'], last)
        require(type(history['next_sequence']) is int and history['next_sequence'] == last
            and last <= accepted and history['complete'] == (last == accepted))
    require(last == accepted)
    for _ in range(1000):
        messages = client.request('POST', '/messages/claim', {'limit': 20})
        require(set(messages) == {'batch_id', 'messages', 'accepted_sequence'}
            and type(messages['accepted_sequence']) is int and messages['accepted_sequence'] == last)
        through = input_page(messages['messages'], last, allow_empty=True)
        if through == last:
            require(messages['batch_id'] is None)
            break
        batch = identifier(messages['batch_id'])
        ack = client.request('POST', '/messages/ack', {'batch_id': batch, 'through_sequence': through})
        require(ack == {'accepted_sequence': through} and type(ack['accepted_sequence']) is int)
        last = through
        if finish_mode == 'off':  # preserve the original bounded default batch
            break
    else:
        raise PluginError('Input work limit exceeded')
    capabilities = client.request('GET', '/capabilities')
    require(type(capabilities.get('capabilities')) is list)
    require(any(c.get('id') == SUMMARY and c.get('allowed') is True and c.get('required') is True
        and c.get('projection') == 'masked' for c in capabilities['capabilities'] if type(c) is dict))
    first = projection(client.request('GET', '/capa/context', query={'view': 'report'}))
    # Canonical state-machine phase plus the original synthetic demo phase.
    require(first['status'] in {'D4_ROOT_CAUSE', 'D4_ANALYSIS'})
    second = projection(client.request('GET', '/capa/context', query={'view': 'verifications',
        'report_id': first['report_id']}), children=True, previous=first)
    receipts = [first['receipt_id'], second['receipt_id']]
    event = client.request('POST', '/events', {'idempotency_key': epoch_key('readonly-8d-query-v1', claim['lease_epoch']),
        'event_type': 'query_completed', 'payload': {'stage': 'D4 metadata', 'completed': 2, 'total': 2},
        'receipt_ids': receipts})
    identifier(event.get('event_id'))
    result = client.request('POST', '/results', {'idempotency_key': epoch_key('readonly-8d-result-v1', claim['lease_epoch']),
        'receipt_ids': receipts, 'payload': metadata_analysis(first, second)})
    identifier(result.get('result_id'))
    require(event.get('task_id') == result.get('task_id') == task_id
        and event.get('run_id') == result.get('run_id') == run_id and result.get('data_class') == 'restricted')
    for output in (event, result):
        require(type(output.get('sources')) is list and len(output['sources']) == 2)
        require({source.get('receipt_id') for source in output['sources']} == set(receipts))
    output = {'task_id': task_id, 'run_id': run_id, 'event_id': event['event_id'], 'result_id': result['result_id']}
    if checkpoint_mode == 'save':
        checkpoint = client.request('POST', '/checkpoints', {
            'idempotency_key': epoch_key('readonly-8d-checkpoint-v1', claim['lease_epoch']),
            'receipt_ids': receipts})
        output['checkpoint_id'] = checkpoint_response(checkpoint, task_id, run_id,
            claim['lease_epoch'], last, [first, second])
    if finish_mode == 'completed':
        # The server serializes completion with append under TASK. A racing new
        # input may safely return 409; never report success after that rejection.
        finished = client.request('POST', '/finish', {'status': 'completed'})
        require(set(finished) == {'task_id', 'task_status', 'run_id', 'run_status', 'lease_epoch'}
            and finished['task_id'] == task_id and finished['run_id'] == run_id
            and finished['task_status'] == finished['run_status'] == 'completed'
            and type(finished['lease_epoch']) is int and finished['lease_epoch'] == claim['lease_epoch']+1)
        output['task_status'] = 'completed'
    print(json.dumps(output))


if __name__ == '__main__':
    try:
        run()
    except Exception:
        # The CLI is the final untrusted-wire boundary: HTTP/parser exceptions
        # can embed peer content. Never print their text or a traceback.
        print('Readonly plugin stopped safely.', file=sys.stderr)
        sys.exit(1)
