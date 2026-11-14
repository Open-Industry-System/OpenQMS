"""Pinned stdlib-only R5 worker. All arguments/results remain platform-owned."""
import http.client
import json
import sys
import time
from urllib.parse import urlsplit


class RetryOriginal(Exception):
    pass


def main():
    config = json.load(sys.stdin)
    origin = urlsplit(config['api_origin'])
    deadline = time.monotonic() + 120
    headers = {'Content-Type':'application/json', 'Authorization':'Bearer '+config['token'],
               'X-Tenant-ID':config['tenant_slug']}

    def request(path, body):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Round expired')
        connection = http.client.HTTPConnection(origin.hostname, origin.port, timeout=min(30, remaining))
        try:
            connection.request('POST', '/api/agent/runtime/'+path, json.dumps(body), headers)
            response = connection.getresponse()
            data = response.read(1024*1024)
            if response.status == 409:
                raise RetryOriginal('Retry original issued ID')
            if response.status != 200:
                raise RuntimeError('Runtime request rejected')
            return json.loads(data)
        finally:
            connection.close()

    # ACK only actual platform-issued message batches, at round entry.
    def accept():
        batch = request('messages/claim', {'limit':20})
        if batch['messages']:
            request('messages/ack', {'batch_id':batch['batch_id'],
                'through_sequence':batch['messages'][-1]['sequence']})
    accept()
    calls = 0
    for turn in range(9):
        response = request('model/infer', {'operation':'workflow', 'turn':turn})
        pending = response['tool_calls']
        if not pending:
            request('finish', {'status':'completed'})
            return
        for call in pending:
            calls += 1
            if calls > 8:
                raise RuntimeError('Tool budget exhausted')
            # A response lost after a write is retried ONLY with this same issued
            # ID, whose server command key and arguments cannot be changed.
            retries = 0
            while True:
                try:
                    result = request('model/tools', {'call_id':call['id']})
                except (OSError, http.client.HTTPException, RetryOriginal):
                    retries += 1
                    if retries > 1:
                        raise
                    continue
                if result.get('status') != 'waiting':
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Round expired')
                time.sleep(.1)
    raise RuntimeError('Round exhausted')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Never put original text, model output, token or credentials on stdout.
        sys.exit(1)
