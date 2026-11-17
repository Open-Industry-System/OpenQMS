"""No-secret attack program used to prove the boundary, not to break it.

Not named `test_*`: pytest must never collect this, and it is copied into the
test image rather than run from the repository.

It runs under exactly the same image, UID, namespaces, cgroup and network rules
as the receiver would. It carries no credential and touches no real data: every
target is either loopback, a self-owned container, or a path that must not be
readable.

Each probe prints one fixed line, `name RESULT detail`, where RESULT is
`ALLOWED` or `DENIED`. The tests assert on those lines; nothing here decides
whether the isolation is good.
"""
import errno
import os
import socket
import sys

SECRET_SENTINEL = 'SENTINEL-NOT-A-REAL-SECRET'


def _line(name, result, detail=''):
    sys.stdout.write('%s %s %s\n' % (name, result, detail))
    sys.stdout.flush()


def probe_network(api_port, target_ip):
    """Only the API tuple may be reachable; everything else must be denied."""
    def tcp(host, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            sock.connect((host, port))
            return 'ALLOWED'
        except OSError:
            return 'DENIED'
        finally:
            sock.close()

    _line('net_api', tcp('127.0.0.1', api_port))
    _line('net_other_loopback', tcp('127.0.0.1', api_port + 1))
    _line('net_external_target', tcp(target_ip, 9000))
    _line('net_metadata', tcp('169.254.169.254', 80))

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.settimeout(3)
    try:
        udp.sendto(b'probe', ('1.1.1.1', 53))
        udp.recvfrom(16)
        _line('net_dns_udp', 'ALLOWED')
    except OSError:
        _line('net_dns_udp', 'DENIED')
    finally:
        udp.close()

    try:
        raw = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
        raw.close()
        _line('net_raw_socket', 'ALLOWED')
    except OSError as error:
        _line('net_raw_socket', 'DENIED', errno.errorcode.get(error.errno, ''))


def probe_files():
    """Host and API secrets must not be readable; the root must not be writable."""
    # `/proc/1` is deliberately not probed: with a private PID namespace it is
    # this container's own init, so reading it is expected, not a leak. Host
    # exposure is checked by counting what the namespace can see instead.
    for path in ('/etc/shadow', '/host', '/srv/openqms'):
        try:
            with open(path, 'rb') as handle:
                handle.read(1)
            _line('file_' + path.replace('/', '_'), 'ALLOWED')
        except OSError:
            _line('file_' + path.replace('/', '_'), 'DENIED')

    try:
        with open('/probe-write', 'wb') as handle:
            handle.write(b'x')
        _line('file_write_root', 'ALLOWED')
    except OSError:
        _line('file_write_root', 'DENIED')


def probe_pid_namespace():
    """A private PID namespace shows only this container's own processes."""
    visible = [name for name in os.listdir('/proc') if name.isdigit()]
    _line('pid_visible_count', str(len(visible)))


def probe_identity():
    """Privilege changes and new namespaces must be impossible."""
    if os.getuid() == 0:
        _line('identity_uid', 'ALLOWED', 'root')
    else:
        _line('identity_uid', 'DENIED', str(os.getuid()))
    try:
        os.setuid(0)
        _line('identity_setuid_root', 'ALLOWED')
    except OSError:
        _line('identity_setuid_root', 'DENIED')
    try:
        os.unshare(os.CLONE_NEWUSER)
        _line('identity_new_userns', 'ALLOWED')
    except (OSError, AttributeError):
        _line('identity_new_userns', 'DENIED')


def probe_output():
    """The controller must stay bounded even if this program never stops."""
    if os.environ.get('ATTACK_UNBOUNDED_OUTPUT') == '1':
        while True:
            sys.stdout.write('x' * 4096)
            sys.stdout.flush()


def main(argv):
    api_port = int(argv[1]) if len(argv) > 1 else 18777
    target_ip = argv[2] if len(argv) > 2 else '127.0.0.1'
    probe_network(api_port, target_ip)
    probe_files()
    probe_pid_namespace()
    probe_identity()
    probe_output()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
