"""Remote helpers shared by the Linux isolation tests."""
import shlex

BASE_IMAGE = 'python@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89'

PROBE = """
import socket,sys
def tcp(host,port,label,fam=socket.AF_INET):
    s=socket.socket(fam,socket.SOCK_STREAM); s.settimeout(3)
    try: s.connect((host,port)); print(label,"REACHABLE")
    except Exception as e: print(label,"BLOCKED",type(e).__name__)
    finally: s.close()
def udp(host,port,label):
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(3)
    try:
        s.sendto(b"x",(host,port)); s.recvfrom(16); print(label,"REACHABLE")
    except Exception as e: print(label,"BLOCKED",type(e).__name__)
    finally: s.close()
tcp("127.0.0.1",18777,"api")
tcp("127.0.0.1",18778,"other")
tcp(sys.argv[1],9000,"target")
tcp("169.254.169.254",80,"metadata")
udp("1.1.1.1",53,"dns_udp")
tcp("::1",18777,"ipv6_loopback",socket.AF_INET6)
"""


def probe(remote, experiment, uid):
    """Run the probe inside the shared namespace as `uid`."""
    script = """
docker run --rm --pull=never --network container:%s --user %d --entrypoint python %s -c %s %s
""" % (experiment.api, uid, shlex.quote(BASE_IMAGE), shlex.quote(PROBE), shlex.quote(experiment.target_ip))
    out = remote(script)
    result = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ('api', 'other', 'target'):
            result[parts[0]] = parts[1]
    return result


def install(remote, experiment, statements):
    """Install the ruleset inside the shared namespace's OUTPUT chain."""
    lines = '\n'.join('sudo nsenter -t %s -n nft %s' % (experiment.pid, shlex.quote(s))
                      for s in statements)
    return remote(lines + '\n')


def listing(remote, experiment):
    return remote('sudo nsenter -t %s -n nft -j list ruleset\n' % experiment.pid)


def remove_table(remote, experiment):
    return remote('sudo nsenter -t %s -n nft delete table inet oqms4 2>/dev/null || true\n'
                  % experiment.pid, check=False)


def statements(policy):
    """The exact nft statements for one policy, in installation order."""
    return (
        'add table inet oqms4',
        'add chain inet oqms4 output { type filter hook output priority 0; policy drop; }',
        'add rule inet oqms4 output meta skuid %d ip daddr 127.0.0.1 tcp dport %d accept'
        % (policy.receiver_uid, policy.api_port),
        'add rule inet oqms4 output meta skuid %d drop' % policy.receiver_uid,
        'add rule inet oqms4 output meta skuid %d accept' % policy.api_uid,
    )
