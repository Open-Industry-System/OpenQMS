"""Owned numeric-loopback wire fixture; no app, SDK, database or DNS."""
import contextlib
import json
import socket
import threading

RUN = '00000000-0000-0000-0000-000000000001'
TASK = '00000000-0000-0000-0000-000000000002'
REPORT = '00000000-0000-0000-0000-000000000003'
INSTALL = '00000000-0000-0000-0000-000000000004'
RECEIPT = '00000000-0000-0000-0000-000000000005'
BATCH = '00000000-0000-0000-0000-000000000006'
MESSAGE = '00000000-0000-0000-0000-000000000007'
START = 'deliver_d4_root_cause_candidate_v1'
CAP = 'capa.d4.root_cause_candidate.masked.v1'
SECRET = 'installation-secret-sentinel'
TOKEN = 'run-token-sentinel'
TEXT = 'candidate-text-sentinel'


def config(origin):
    return dict(origin=origin, tenant_slug='owned-test', installation_id=INSTALL,
                secret=SECRET, request_key='owned-request', expected_report_id=REPORT)


def responses():
    return [dict(run_id=RUN, task_id=TASK, token=TOKEN, lease_epoch=1,
                 lease_expires_at='2026-11-13T10:00:00Z', accepted_message_seq=0,
                 has_resume_checkpoint=False),
            dict(capabilities=[dict(id=CAP, allowed=True, required=True, projection='masked')]),
            dict(batch_id=BATCH, messages=[dict(message_id=MESSAGE, sequence=1, content=START)], accepted_sequence=0),
            dict(protocol='1', run_id=RUN, task_id=TASK, report_id=REPORT,
                 recipient_installation_id=INSTALL, plugin_version='1.0.0', receipt_id=RECEIPT,
                 generated_at='2026-11-13T10:00:00Z', projection_id=CAP,
                 data_class='restricted', projection='masked', candidate_kind='redaction_candidate',
                 declassification_status='not_approved', source_proof='employee_declared_complete_v1',
                 source_authorization='current', model_delivery_allowed=False, delivery_scope='local_plugin_only',
                 rule_version='capa.d4.redaction.v1', source_version='a'*64, source_proof_digest='b'*64,
                 policy_binding='c'*64, projection_digest='d'*64, field='d4_root_cause', text=TEXT),
            dict(accepted_sequence=1),
            dict(run_id=RUN, task_id=TASK, run_status='completed', task_status='completed', lease_epoch=2)]


def reply(body, headers=None):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n' +
            (headers if headers is not None else b'Content-Length: '+str(len(raw)).encode()+b'\r\n') + b'\r\n'+raw)


@contextlib.contextmanager
def server(replies, *, tls_context=None):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(.1)
    stop = threading.Event()
    requests = []
    errors = []

    def serve():
        try:
            for response in replies:
                while not stop.is_set():
                    try:
                        conn, _ = listener.accept()
                        break
                    except socket.timeout:
                        continue
                else:
                    return
                if tls_context is not None:
                    conn = tls_context.wrap_socket(conn, server_side=True)
                with conn:
                    conn.settimeout(2)
                    raw = b''
                    while b'\r\n\r\n' not in raw:
                        piece = conn.recv(4096)
                        if not piece:
                            raise ConnectionResetError()
                        raw += piece
                    head, body = raw.split(b'\r\n\r\n', 1)
                    headers = dict(line.split(b': ', 1) for line in head.split(b'\r\n')[1:])
                    size = int(headers.get(b'Content-Length', b'0'))
                    while len(body) < size:
                        piece = conn.recv(4096)
                        if not piece:
                            raise ConnectionResetError()
                        body += piece
                    requests.append((head.split(b'\r\n')[0], headers, body))
                    if callable(response):
                        response(conn)
                    else:
                        conn.sendall(response if isinstance(response, bytes) else reply(response))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            if not stop.is_set():
                errors.append(type(exc).__name__)
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield ('https' if tls_context is not None else 'http')+'://127.0.0.1:'+str(listener.getsockname()[1]), requests
    finally:
        stop.set()
        thread.join(3)
        listener.close()
        assert not thread.is_alive()
        assert not errors, errors
