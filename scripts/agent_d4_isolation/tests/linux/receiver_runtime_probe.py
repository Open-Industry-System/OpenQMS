"""Trusted, secret-free remote probe; invoked explicitly, never collected."""
import json
import secrets
import subprocess
import sys
import time

IMAGE = sys.argv[1]
NONCE = secrets.token_hex(12)
FLAGS = ['--pull=never', '--user', '2001:2001', '--cap-drop', 'ALL',
         '--security-opt', 'no-new-privileges', '--read-only',
         '--tmpfs', '/tmp:rw,nodev,nosuid,noexec,size=8m,nr_inodes=128',
         '--memory', '128m', '--memory-swap', '128m', '--pids-limit', '16',
         '--cpus', '1', '--ulimit', 'nofile=64:64', '--ulimit', 'core=0:0',
         '--log-driver', 'none']
owned = []


def docker(*args, **kwargs):
    return subprocess.run(['docker', *args], check=True, capture_output=True,
                          text=True, timeout=40, **kwargs).stdout.strip()


def create(name, *args):
    identity = docker('create', '--name', name, *args)
    assert len(identity) == 64
    owned.append(identity)
    return identity


def absent(identity):
    result = subprocess.run(['docker', 'inspect', identity], capture_output=True, text=True)
    assert result.returncode != 0 and any(x in result.stderr.lower() for x in ('no such object', 'no such container'))


try:
    code = '''import json,resource
from pathlib import Path
mount=next(x for x in Path('/proc/mounts').read_text().splitlines() if x.split()[1]=='/tmp')
print(json.dumps(dict(mount=mount,memory=Path('/sys/fs/cgroup/memory.max').read_text().strip(),
swap=Path('/sys/fs/cgroup/memory.swap.max').read_text().strip(),
pids=Path('/sys/fs/cgroup/pids.max').read_text().strip(),
cpu=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),
nofile=resource.getrlimit(resource.RLIMIT_NOFILE),core=resource.getrlimit(resource.RLIMIT_CORE))))'''
    readback = create('oqms-d4-readback-' + NONCE, *FLAGS, '--network', 'none',
                      '--entrypoint', 'python', IMAGE, '-I', '-S', '-B', '-c', code)
    facts = json.loads(docker('start', '-a', readback))
    options = set(facts['mount'].split()[3].split(','))
    assert {'nodev', 'nosuid', 'noexec', 'size=8192k', 'nr_inodes=128'} <= options, facts
    assert facts['memory'] == '134217728' and facts['swap'] == '0', facts
    assert facts['pids'] == '16', facts
    quota, period = map(int, facts['cpu'].split())
    assert quota == period and quota > 0, facts
    assert facts['nofile'] == [64, 64] and facts['core'] == [0, 0], facts
    print('kernel_limits_ok', json.dumps(facts, sort_keys=True), flush=True)

    # The owned wire fixture is a protocol control, never I9 application evidence.
    # A valid claim padded to exactly the cap must complete all six requests.
    server = WIRE_FIXTURE_SOURCE + r"""
import sys,time
s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind(('127.0.0.1',18777));s.listen();print('listening',flush=True)
mode=sys.argv[1]
for index,payload in enumerate(responses()):
 c,_=s.accept()
 with c:
  c.recv(65536);print('request_seen',index,flush=True)
  raw=json.dumps(payload).encode()
  if index==0:
   size=262145 if mode=='large' else 262144
   raw=raw+b' '*(size-len(raw))
  header=b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nContent-Length: '+str(len(raw)).encode()+b'\r\n\r\n'
  try:
   if mode=='slow' and index==0:
    c.sendall(header+raw[:1]);time.sleep(15);c.sendall(raw[1:])
   else:c.sendall(header+raw)
  except (BrokenPipeError,ConnectionResetError):break
time.sleep(30)
"""
    for mode in ('control', 'large', 'slow'):
        api = create('oqms-d4-wire-' + mode + '-' + NONCE, '--pull=never',
                     '--network', 'none', '--user', '2002:2002', '--cap-drop', 'ALL',
                     '--security-opt', 'no-new-privileges', '--memory', '128m',
                     '--pids-limit', '16', '--entrypoint', 'python', IMAGE,
                     '-I', '-S', '-B', '-u', '-c', server, mode)
        docker('start', api)
        for _ in range(100):
            if 'listening' in docker('logs', api):
                break
            time.sleep(.05)
        else:
            raise AssertionError('owned wire listener failed')
        variant = globals().get('MUTATION')
        entry = []
        command = []
        if variant:
            entry = ['--entrypoint', 'python']
            old, new = {'size': ('RESPONSE_LIMIT = 256 * 1024', 'RESPONSE_LIMIT = 512 * 1024'),
                        'deadline': ('OPERATION_SECONDS = 10', 'OPERATION_SECONDS = 20')}[variant]
            mutant = ('source=open("/receiver.py").read();'
                      'assert source.count(' + repr(old) + ')==1;'
                      'exec(compile(source.replace(' + repr(old) + ',' + repr(new) + '),"/receiver.py","exec"),{"__name__":"__main__"})')
            command = ['-I', '-S', '-B', '-c', mutant]
        receiver = create('oqms-d4-receiver-' + mode + '-' + NONCE, '-i', *FLAGS,
                          '--network', 'container:' + api, *entry, IMAGE, *command)
        config = dict(origin='http://127.0.0.1:18777', tenant_slug='owned-test',
                      installation_id='00000000-0000-0000-0000-000000000004',
                      secret='synthetic-no-authority-secret', request_key=NONCE,
                      expected_report_id='00000000-0000-0000-0000-000000000003')
        before = time.monotonic()
        result = subprocess.run(['docker', 'start', '-a', '-i', receiver],
                                input=json.dumps(config), capture_output=True,
                                text=True, timeout=20)
        elapsed = time.monotonic() - before
        status = json.loads(result.stdout)
        if mode == 'control':
            assert result.returncode == 0 and status['status'] == 'completed', status
            assert status['received_fields'] == 1
            assert 'request_seen 5' in docker('logs', api)
        else:
            assert result.returncode != 0 and status['received_fields'] == 0, (
                'oversize_was_accepted' if mode == 'large' else 'deadline_was_accepted')
            assert status['status'] != 'completed'
            assert 'request_seen 1' not in docker('logs', api)
        assert 'request_seen' in docker('logs', api), mode
        assert config['secret'] not in result.stdout + result.stderr
        if mode == 'slow':
            assert 9 <= elapsed < 14, elapsed
        else:
            assert elapsed < 8, elapsed
        print({'control': 'positive_control_ok', 'large': 'oversize_denied',
               'slow': 'deadline_denied'}[mode], round(elapsed, 3), flush=True)
        # Remove each pair before proceeding; no parallel experiments.
        for identity in (receiver, api):
            docker('rm', '-f', identity)
            absent(identity)
            owned.remove(identity)
finally:
    failures = []
    for identity in reversed(owned):
        try:
            docker('rm', '-f', identity)
            absent(identity)
        except Exception as error:
            failures.append((identity, type(error).__name__))
    if failures:
        raise RuntimeError('cleanup_unverified: ' + repr(failures))
    print('cleanup_verified', flush=True)
