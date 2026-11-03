import socket
import threading

import pytest

from openqms_agent_sdk._deadline import Deadline
from openqms_agent_sdk._transport import Resolver
from openqms_agent_sdk.errors import RequestTimeout, TransportError
from test_deadline import no_network


def test_timeout_late_result_busy_and_close(monkeypatch):
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def lookup(host, port, *args, **kwargs):
        calls.append((host, port))
        entered.set()
        release.wait(2)
        returned.set()
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', port))]
    monkeypatch.setattr(socket, 'getaddrinfo', lookup)
    resolver = Resolver()
    try:
        with pytest.raises(RequestTimeout):
            resolver.resolve('test.invalid', 443, Deadline(.02, 'claim'))
        assert entered.is_set()
        with pytest.raises(TransportError) as caught:
            resolver.resolve('test.invalid', 443, Deadline(1, 'claim'))
        assert caught.value.kind == 'dns_busy'
        assert len(calls) == 1
        resolver.close()
        assert resolver._thread.daemon
    finally:
        release.set()
        assert returned.wait(1)
        resolver.close()


def test_late_dns_result_can_never_connect_send_or_accumulate_jobs(monkeypatch):
    from openqms_agent_sdk._transport import Transport
    from openqms_agent_sdk.models import ClientConfig, EncodedRequest
    release, entered = threading.Event(), threading.Event()
    lookups, sockets = [], []
    def lookup(host, port, **kwargs):
        lookups.append((host, port))
        entered.set()
        assert release.wait(2)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.0.2.1', port))]
    def socket_factory(*args, **kwargs):
        sockets.append(args)
        raise AssertionError('late DNS must never connect')
    monkeypatch.setattr(socket, 'getaddrinfo', lookup)
    monkeypatch.setattr(socket, 'socket', socket_factory)
    transport = Transport(ClientConfig('https://test.invalid'))
    resolver = transport._resolver
    try:
        with pytest.raises(RequestTimeout) as caught:
            transport.exchange('claim', token='not-in-worker', request=EncodedRequest(b'secret-body', ()), deadline=Deadline(.02, 'claim'))
        assert not caught.value.may_have_been_sent
        assert entered.is_set()
        thread, job = resolver._thread, resolver._active
        assert job[2].maxsize == 1 and job[3].is_set()
        assert job[:2] == ('test.invalid', 443)
        for _ in range(10):
            with pytest.raises(TransportError) as busy:
                transport.exchange('claim', token=None, request=EncodedRequest(b'{}', ()), deadline=Deadline(1, 'claim'))
            assert busy.value.kind == 'dns_busy' and not busy.value.may_have_been_sent
            assert resolver._thread is thread
            assert resolver._jobs.empty()
        transport.close()  # must return while the OS lookup remains blocked
        assert thread.is_alive()
        release.set()
        thread.join(1)
        assert not thread.is_alive()
        assert job[2].empty() and resolver._active is None
        assert len(lookups) == 1 and sockets == []
    finally:
        release.set()
        transport.close()
        if resolver._thread is not None:
            resolver._thread.join(1)


def test_numeric_and_localhost_never_start_dns_helper():
    resolver = Resolver()
    try:
        for host, expected in [('127.0.0.1', '127.0.0.1'), ('::1', '::1'), ('localhost', '127.0.0.1')]:
            result = resolver.resolve(host, 12345, Deadline(1, 'claim'))
            assert result[0][4][0] == expected
        assert resolver._thread is None
    finally:
        resolver.close()


def test_dns_exception_retains_no_original_context(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('secret.invalid token body')
    monkeypatch.setattr(socket, 'getaddrinfo', fail)
    resolver = Resolver()
    try:
        with pytest.raises(TransportError) as caught:
            resolver.resolve('test.invalid', 443, Deadline(1, 'claim'))
        assert caught.value.kind == 'dns'
        assert caught.value.__context__ is None
        assert 'secret' not in str(caught.value)
    finally:
        resolver.close()
