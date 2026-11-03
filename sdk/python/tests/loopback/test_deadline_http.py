"""NON-PURE: owned random-port loopback HTTP only, never live DNS."""
import time

import pytest

from openqms_agent_sdk._deadline import Deadline
from openqms_agent_sdk._transport import Transport
from openqms_agent_sdk.errors import RequestTimeout
from openqms_agent_sdk.models import ClientConfig, EncodedRequest

HEADER = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
CHUNK = HEADER + b'Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n'


@pytest.mark.parametrize('prefix,drip', [
    (b'', b'HTTP/1.1 200 OK\r\n'),
    (b'HTTP/1.1 200 OK\r\n', b'Content-Type: application/json\r\n'),
    (HEADER + b'Content-Length: 10\r\nConnection: close\r\n\r\n', b'0123456789'),
    (CHUNK, b'00000002;ok=yes\r\n'),
    (CHUNK + b'2;', b'name=value\r\n'),
    (CHUNK + b'2\r\n{}', b'\r\n0\r\n\r\n'),
    (CHUNK + b'2\r\n{}\r\n0\r\n', b'X-End: yes\r\n\r\n'),
    (b'HTTP/1.1 100 Continue\r\n', b'X-Wait: yes\r\n\r\n'),
])
def test_slow_drips_obey_whole_operation_deadline(serve, prefix, drip):
    parts = [(0, prefix)] + [(.04, bytes([byte])) for byte in drip]
    url, requests = serve(parts)
    transport = Transport(ClientConfig(url))
    started = time.monotonic()
    try:
        with pytest.raises(RequestTimeout) as caught:
            transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(.14, 'claim'))
        elapsed = time.monotonic() - started
        assert .09 < elapsed < .8
        assert caught.value.kind == 'deadline'
        assert caught.value.may_have_been_sent
        assert caught.value.__context__ is None
        assert len(requests) == 1
    finally:
        transport.close()


@pytest.mark.parametrize('wire', [
    HEADER + b'Content-Length: 2\r\nConnection: close\r\n\r\n{}',
    HEADER + b'Connection: close\r\n\r\n{}',
    CHUNK + b'2;name=value\r\n{}\r\n0\r\nX-End: yes\r\n\r\n',
    b'HTTP/1.1 100 Continue\r\nX-Interim: yes\r\n\r\n' + HEADER + b'Content-Length: 2\r\nConnection: close\r\n\r\n{}',
])
@pytest.mark.parametrize('host', ['127.0.0.1', '::1'])
def test_connection_close_still_allows_response_body(serve, wire, host):
    url, requests = serve([(0, wire)], host=host)
    transport = Transport(ClientConfig(url))
    try:
        response = transport.exchange('claim', token='not-sent', request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
        assert response.body == b'{}' and response.status == 200
        assert response.may_have_been_sent
        assert len(requests) == 1
        assert b'Authorization:' not in requests[0]
        assert b'Connection: close\r\n' in requests[0]
    finally:
        transport.close()
