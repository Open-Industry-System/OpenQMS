"""Explicit NON-PURE fixtures: only test-owned numeric loopback port-zero services."""
import socket
import threading

import pytest


@pytest.fixture(autouse=True)
def owned_loopback_only(monkeypatch):
    original = socket.socket
    owned = set()

    class OwnedSocket(original):
        def __init__(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
            assert family in (socket.AF_INET, socket.AF_INET6)
            super().__init__(family, type, proto, fileno)

        def bind(self, address):
            assert address[0] in ('127.0.0.1', '::1') and address[1] == 0
            super().bind(address)
            owned.add(self.getsockname()[:2])

        def connect(self, address):
            assert address[:2] in owned, 'only fixture-owned loopback endpoints'
            return super().connect(address)

        def connect_ex(self, address):
            assert address[:2] in owned
            return super().connect_ex(address)

    def deny(*args, **kwargs):
        raise AssertionError('no DNS or ambient connections in loopback tests')

    monkeypatch.setattr(socket, 'socket', OwnedSocket)
    for name in ('getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr', 'getnameinfo', 'create_connection'):
        monkeypatch.setattr(socket, name, deny)
    return owned


@pytest.fixture
def serve(owned_loopback_only):
    services = []

    def start(parts, *, host='127.0.0.1'):
        family = socket.AF_INET6 if host == '::1' else socket.AF_INET
        listener = socket.socket(family, socket.SOCK_STREAM)
        stop = threading.Event()
        connections, requests, failures = [], [], []
        thread = None
        try:
            listener.bind((host, 0))
            listener.listen(1)
            listener.settimeout(.1)
            address = listener.getsockname()

            def run():
                connection = None
                try:
                    while not stop.is_set():
                        try:
                            connection, _ = listener.accept()
                            break
                        except socket.timeout:
                            continue
                    if connection is None:
                        return
                    connections.append(connection)
                    connection.settimeout(.5)
                    request = bytearray()
                    while b'\r\n\r\n' not in request and len(request) <= 1024 * 1024:
                        piece = connection.recv(4096)
                        if not piece:
                            return
                        request.extend(piece)
                    head, body = bytes(request).split(b'\r\n\r\n', 1)
                    length = 0
                    for line in head.split(b'\r\n')[1:]:
                        if line.lower().startswith(b'content-length:'):
                            length = int(line.split(b':', 1)[1])
                    while len(body) < length:
                        piece = connection.recv(min(4096, length - len(body)))
                        if not piece:
                            return
                        body += piece
                    requests.append(bytes(request))
                    for delay, chunk in parts:
                        if stop.wait(delay):
                            return
                        connection.sendall(chunk)
                except OSError:
                    # The caller may time out and close during a planned drip.
                    pass
                except Exception as exc:
                    failures.append(type(exc).__name__)
                finally:
                    if connection is not None:
                        connection.close()

            thread = threading.Thread(target=run, name='sdk-owned-loopback', daemon=True)
            thread.start()
            services.append((stop, listener, connections, thread, failures))
            bracket_host = f'[{host}]' if ':' in host else host
            return f'http://{bracket_host}:{address[1]}', requests
        except BaseException:
            stop.set()
            listener.close()
            if thread is not None:
                thread.join(2)
            raise

    try:
        yield start
    finally:
        for stop, listener, connections, thread, failures in services:
            stop.set()
            listener.close()
            for connection in connections:
                connection.close()
            thread.join(2)
            assert not thread.is_alive(), 'owned server must terminate'
            assert not failures, failures
