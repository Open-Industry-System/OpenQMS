import pytest
from openqms_agent_sdk._deadline import Deadline
from openqms_agent_sdk.errors import RequestTimeout


def test_one_absolute_budget():
    now = [5.0]
    deadline = Deadline(2, 'finish', clock=lambda: now[0])
    assert deadline.remaining() == 2
    now[0] = 6.5
    assert deadline.remaining() == .5
    now[0] = 7
    with pytest.raises(RequestTimeout) as caught:
        deadline.check()
    assert caught.value.kind == 'deadline'
    assert caught.value.operation == 'finish'
    assert caught.value.__context__ is None


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    def deny(*a, **kw):
        raise AssertionError('pure test attempted network')
    for name in ('socket', 'getaddrinfo', 'create_connection', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr', 'getnameinfo'):
        monkeypatch.setattr(socket, name, deny)


def test_remaining_checks_expiry():
    deadline = Deadline(0, 'claim', clock=lambda: 1)
    with pytest.raises(RequestTimeout):
        deadline.remaining()
