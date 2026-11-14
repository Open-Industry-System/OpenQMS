"""No sockets: real http.client parsing over a reference-counted fake stream."""
import io


class FakeRaw(io.RawIOBase):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        owner.refs += 1

    def readable(self):
        return True

    def readinto(self, buffer):
        owner = self.owner
        assert not owner.released
        owner.advance('read')
        amount = min(len(buffer), owner.read_size, len(owner.incoming))
        buffer[:amount] = owner.incoming[:amount]
        del owner.incoming[:amount]
        return amount

    def close(self):
        if not self.closed:
            self.owner.refs -= 1
            self.owner.release_if_unused()
        super().close()


class FakeSocket:
    def __init__(self, incoming=b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}', *, clock=None, delays=None, read_size=65536, send_size=65536):
        self.incoming = bytearray(incoming)
        self.clock = clock
        self.delays = delays or {}
        self.read_size, self.send_size = read_size, send_size
        self.sent = bytearray()
        self.timeouts = []
        self.events = []
        self.refs = 0
        self.closed = False
        self.released = False

    def advance(self, phase):
        self.events.append(phase)
        if self.clock is not None:
            self.clock[0] += self.delays.get(phase, 0)

    def settimeout(self, timeout):
        assert timeout > 0
        self.timeouts.append(timeout)

    def connect(self, address):
        self.address = address
        self.advance('connect')

    def send(self, data):
        assert not self.released
        self.advance('send')
        amount = min(len(data), self.send_size)
        self.sent.extend(data[:amount])
        return amount

    def makefile(self, mode, *, buffering):
        assert mode == 'rb' and buffering == 0
        return FakeRaw(self)

    def close(self):
        self.closed = True
        self.release_if_unused()

    def release_if_unused(self):
        if self.closed and self.refs == 0:
            self.released = True
