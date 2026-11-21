"""Authority-free attack overlay under the current recipe; not delivery evidence.

Only Entrypoint differs. A test-local observer checks that exact overlay before
normalizing this one field for KernelCollector. Production admission is intact.
"""
import copy
import errno
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
import types

H = None
LABEL = 'org.openqms.d4.boundary.nonce'
ROLE = 'org.openqms.d4.boundary.role'
PRE_NETWORK = ('api', 'other_loopback', 'target')
POST_NETWORK = ('api', 'other_loopback', 'target', 'dns_tcp', 'gateway', 'metadata')
SYSCALLS = ('udp', 'ipv6', 'unix', 'netlink', 'packet', 'raw', 'bind', 'listen',
            'userns', 'setns', 'ptrace', 'setuid', 'mount')
MOUNT_FLAGS = ('nodev', 'nosuid', 'noexec', 'size=8192k', 'nr_inodes=128')
ENTRY = ['python', '-I', '-S', '-B', '/receiver.py']


class BoundaryFailure(Exception):
    pass


def require(value, code):
    if not value:
        raise BoundaryFailure(code)


def validate_results(pre, post):
    require(type(pre) is dict and set(pre) == {'phase', 'uid', 'network'}, 'pre_shape_invalid')
    require(pre['phase'] == 'pre' and type(pre['uid']) is int and pre['uid'] == 2001, 'pre_identity_invalid')
    require(type(pre['network']) is dict and set(pre['network']) == set(PRE_NETWORK), 'pre_vectors_missing')
    require(all(type(value) is int and value == 0 for value in pre['network'].values()), 'positive_control_failed')
    require(type(post) is dict and set(post) == {'phase', 'uid', 'network', 'syscalls', 'files', 'mounts'}, 'post_shape_invalid')
    require(post['phase'] == 'post' and type(post['uid']) is int and post['uid'] == 2001, 'post_identity_invalid')
    require(type(post['network']) is dict and set(post['network']) == set(POST_NETWORK), 'network_vectors_missing')
    require(post['network']['api'] == 0, 'api_not_allowed')
    require(all(type(value) is int and value == errno.ETIMEDOUT for key, value in post['network'].items() if key != 'api'),
            'tcp_not_dropped')
    require(type(post['syscalls']) is dict and set(post['syscalls']) == set(SYSCALLS), 'syscall_vectors_missing')
    require(all(type(value) is int and value == errno.EPERM for value in post['syscalls'].values()), 'syscall_not_denied')
    require(type(post['files']) is dict and set(post['files']) == {'host_file', 'api_file', 'root_write', 'tmp_exec'}, 'file_vectors_missing')
    require(all(type(post['files'][key]) is int and post['files'][key] in (errno.ENOENT, errno.EACCES)
                for key in ('host_file', 'api_file')), 'private_file_exposed')
    require(post['files']['root_write'] == errno.EROFS and post['files']['tmp_exec'] == errno.EACCES, 'mount_boundary_failed')
    require(type(post['mounts']) is dict and set(post['mounts']) == set(MOUNT_FLAGS) and
            all(value is True for value in post['mounts'].values()), 'mount_flags_missing')


class OverlayObserver:
    """Test-only single-field exception; never installed in the runtime package."""
    def __init__(self, engine, cid, image_id, entry):
        self.engine, self.cid, self.image_id, self.entry = engine, cid, image_id, entry

    def inspect(self, cid, deadline_ns):
        raw = self.engine.inspect(cid, deadline_ns)
        if cid != self.cid:
            return raw
        require(raw['Id'] == self.cid and raw['Image'] == self.image_id and
                raw['Config']['Entrypoint'] == self.entry, 'overlay_identity_changed')
        result = copy.deepcopy(raw)
        result['Config']['Entrypoint'] = list(ENTRY)
        return result

    def info(self, deadline_ns): return self.engine.info(deadline_ns)
    def inspect_image(self, image_id, deadline_ns): return self.engine.inspect_image(image_id, deadline_ns)
    def signal(self, cid, signum, deadline_ns): return self.engine.signal(cid, signum, deadline_ns)


def helpers():
    module = types.ModuleType('_boundary_wiring_helpers')
    module.__dict__.update(PACKAGE_B64=PACKAGE_B64, PACKAGE_SHA256=PACKAGE_SHA256, WIRE_FIXTURE_SOURCE=WIRE_FIXTURE_SOURCE)
    exec(compile(WIRING_PROBE_SOURCE, '<trusted-wiring-helpers>', 'exec'), module.__dict__)
    return module


SERVER = r'''
import os,select,socket,time
ROLE=CONFIG['role']; target=CONFIG['target']; listeners={}
if ROLE=='api':
 fd=os.open(CONFIG['api_file'],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 os.write(fd,b'SYNTHETIC-BOUNDARY-ONLY');os.close(fd)
 with open(CONFIG['api_file'],'rb') as f:assert f.read()==b'SYNTHETIC-BOUNDARY-ONLY'
for port in ((18777,18778) if ROLE=='api' else (19000,)):
 s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
 s.bind(('127.0.0.1' if ROLE=='api' else '0.0.0.0',port));s.listen(8);listeners[port]=s
print('ready',flush=True)
while True:
 readable,_,_=select.select(list(listeners.values()),[],[],1)
 for listener in readable:
  c,_=listener.accept()
  with c:
   c.settimeout(1)
   try:
    message=c.recv(64)
    if message==b'CLOSE_OTHER' and ROLE=='api':
     listeners.pop(18778).close();print('other_closed',flush=True)
    if message==b'CHECK_TARGET' and ROLE=='api':
     with socket.create_connection((target,19000),timeout=1) as peer:
      peer.sendall(b'PING');assert peer.recv(16)==b'OK'
     print('downstream_ok',flush=True)
    c.sendall(b'OK')
   except OSError:pass
'''

ATTACK = r'''
import ctypes,errno,json,os,socket,sys
libc=ctypes.CDLL(None,use_errno=True)
def code(operation):
 try:
  operation();return 0
 except OSError as e:
  if isinstance(e,TimeoutError):return errno.ETIMEDOUT
  if type(e.errno) is not int:raise RuntimeError('missing_errno')
  return e.errno
def call(name,*args):
 ctypes.set_errno(0)
 result=getattr(libc,name)(*args)
 if result==-1:
  number=ctypes.get_errno()
  if not number:raise RuntimeError('missing_libc_errno')
  return number
 return 0
def tcp(host,port,exchange=False,message=b'PING'):
 def connect():
  with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
   s.settimeout(.4);s.connect((host,port))
   if exchange:
    s.sendall(message)
    if s.recv(16)!=b'OK':raise RuntimeError('positive_peer_invalid')
 return code(connect)
def family(domain,kind,protocol=0):
 def create():
  s=socket.socket(domain,kind,protocol);s.close()
 return code(create)
def emit(row):print(json.dumps(row,sort_keys=True),flush=True)
try:
 if sys.stdin.readline()!='PRE\n':raise RuntimeError('command_invalid')
 pre=dict(phase='pre',uid=os.getuid(),network=dict(api=tcp('127.0.0.1',18777,True),
    other_loopback=tcp('127.0.0.1',18778,True),target=tcp(CONFIG['target'],19000,True)))
 if tcp('127.0.0.1',18777,True,b'CLOSE_OTHER')!=0:raise RuntimeError('listener_close_failed')
 emit(pre)
 if sys.stdin.readline()!='POST\n':raise RuntimeError('command_invalid')
 network=dict(api=tcp('127.0.0.1',18777,True),other_loopback=tcp('127.0.0.1',18778),
   target=tcp(CONFIG['target'],19000),dns_tcp=tcp(CONFIG['target'],53),
   gateway=tcp(CONFIG['gateway'],19000),metadata=tcp('169.254.169.254',80))
 if tcp('127.0.0.1',18777,True,b'CHECK_TARGET')!=0:raise RuntimeError('target_control_failed')
 syscalls=dict(udp=family(socket.AF_INET,socket.SOCK_DGRAM),ipv6=family(socket.AF_INET6,socket.SOCK_STREAM),
   unix=family(socket.AF_UNIX,socket.SOCK_STREAM),netlink=family(socket.AF_NETLINK,socket.SOCK_RAW),
   packet=family(socket.AF_PACKET,socket.SOCK_RAW),raw=family(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_RAW))
 with socket.socket() as sock:
  syscalls['bind']=code(lambda:sock.bind(('127.0.0.1',0)))
  syscalls['listen']=call('listen',sock.fileno(),1)
 syscalls.update(userns=call('unshare',0x10000000),setns=call('setns',-1,0),
   ptrace=call('ptrace',16,CONFIG['api_pid'],0,0),setuid=call('setuid',0),
   mount=call('mount',b'none',b'/tmp',b'tmpfs',0,None))
 def read_file(path):
  with open(path,'rb') as f:f.read(1)
 def write_root():
  with open('/boundary-root-write','wb') as f:f.write(b'x')
 files=dict(host_file=code(lambda:read_file(CONFIG['host_file'])),
   api_file=code(lambda:read_file(CONFIG['api_file'])),root_write=code(write_root))
 rows=[line.split() for line in open('/proc/self/mountinfo')]
 tmp=next(row for row in rows if row[4]=='/tmp');sep=tmp.index('-')
 options=set(tmp[5].split(','))|set(tmp[sep+3].split(','))
 mounts={key:key in options for key in ('nodev','nosuid','noexec','size=8192k','nr_inodes=128')}
 with open('/tmp/boundary-exec','w') as f:f.write('#!'+sys.executable+'\nprint("unexpected_exec")\n')
 os.chmod('/tmp/boundary-exec',0o700)
 files['tmp_exec']=code(lambda:os.execve('/tmp/boundary-exec',['/tmp/boundary-exec'],{}))
 emit(dict(phase='post',uid=os.getuid(),network=network,syscalls=syscalls,files=files,mounts=mounts))
 if sys.stdin.readline()!='END\n':raise RuntimeError('command_invalid')
except Exception:
 emit(dict(phase='error',code='attack_exception'));raise SystemExit(1)
'''


def attack_source(config):
    require(set(config) == {'target', 'gateway', 'api_pid', 'host_file', 'api_file'}, 'attack_config_invalid')
    for key in ('target', 'gateway'): ipaddress.IPv4Address(config[key])
    require(type(config['api_pid']) is int and config['api_pid'] > 1, 'api_pid_invalid')
    return 'CONFIG=' + repr(config) + '\n' + ATTACK


def assert_owned(cid, receipt, role):
    raw = H.inspect(cid)
    require(raw['Id'] == cid and raw['Image'] == receipt['image_id'] and
            raw['Config'].get('Labels', {}).get(LABEL) == receipt['nonce'] and
            raw['Config']['Labels'].get(ROLE) == role, 'resource_identity_changed')
    return raw


def cleanup_objects(receipt):
    errors = []
    for row in reversed(receipt['objects']):
        try:
            assert_owned(row['id'], receipt, row['role'])
            H.docker('rm', '-f', row['id']); H.absent(row['id'])
        except Exception:
            errors.append(row['role'] + '_cleanup_unknown')
    if any(receipt.get('create_pending', {}).values()):
        errors.append('create_unresolved')
    receipt['cleanup_errors'] = errors
    return not errors


def create_server(role, target, receipt):
    api_file = '/tmp/api-boundary-' + receipt['nonce']
    source = 'CONFIG=' + repr(dict(role=role, target=target, api_file=api_file)) + '\n' + SERVER
    receipt['create_pending'][role] = True; H.record_receipt(receipt)
    result = H.docker('create', '--pull=never', '--name', 'oqms-d4-boundary-' + role + '-' + receipt['nonce'],
        '--label', LABEL + '=' + receipt['nonce'], '--label', ROLE + '=' + role,
        '--network', 'bridge', '--user', '2002:2002', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--read-only', '--memory', '128m', '--memory-swap', '128m',
        '--pids-limit', '16', '--cpus', '1', '--ulimit', 'core=0:0',
        '--tmpfs', '/tmp:rw,nodev,nosuid,noexec,size=8m,nr_inodes=128',
        '--log-driver', 'json-file', '--log-opt', 'max-size=16k', '--log-opt', 'max-file=1',
        '--entrypoint', 'python', receipt['image_id'], '-I', '-S', '-B', '-c', source)
    cid = result.stdout.decode('ascii').strip(); require(re.fullmatch('[a-f0-9]{64}', cid), 'create_unknown')
    receipt['objects'].append(dict(id=cid, role=role)); receipt['create_pending'][role] = False; H.record_receipt(receipt)
    assert_owned(cid, receipt, role); H.docker('start', cid)
    deadline = time.monotonic_ns() + 5_000_000_000
    while time.monotonic_ns() < deadline:
        if H.docker('logs', cid).stdout.decode('ascii').splitlines() == ['ready']: return cid
        time.sleep(.02)
    raise BoundaryFailure('server_not_ready')


def read_row(chunks):
    raw = bytearray()
    while len(raw) <= 8192:
        piece = next(chunks)
        require(len(piece) <= 512, 'attach_chunk_unbounded')
        raw.extend(piece)
        if raw.endswith(b'\n'):
            require(raw.count(b'\n') == 1, 'unexpected_output_lines')
            return json.loads(raw)
    raise BoundaryFailure('attack_output_limit')


def write_all(channel, command, deadline):
    offset = 0
    while offset < len(command):
        count = channel.write(command[offset:], deadline)
        require(type(count) is int and 0 < count <= len(command) - offset, 'command_write_failed')
        offset += count


def main(image_tag):
    global H
    require(os.geteuid() == 0, 'root_required')
    H = helpers()
    receipt = dict(nonce=H.NONCE, root=str(H.ROOT), objects=[], boundary_verified=False,
        create_pending=dict(api=False, target=False, receiver=False),
        resources_cleaned=False, failure_code=None, controller_delivery_evidence=False,
        entrypoint_overlay_only=True, bundle_sha256=PACKAGE_SHA256, probe_sha256=PROBE_SHA256)
    channel = binding = lease = None
    try:
        H.unpack_package(); H.record_receipt(receipt)
        images = json.loads(H.docker('image', 'inspect', image_tag).stdout)
        require(len(images) == 1 and re.fullmatch('sha256:[a-f0-9]{64}', images[0]['Id']), 'image_invalid')
        receipt['image_id'] = images[0]['Id']
        target_id = create_server('target', '127.0.0.1', receipt)
        target = H.inspect(target_id)['NetworkSettings']['Networks']['bridge']['IPAddress']
        api_id = create_server('api', target, receipt)
        api = H.inspect(api_id); gateway = api['NetworkSettings']['Networks']['bridge']['Gateway']
        host_file = H.ROOT / 'private/host-sentinel.json'
        H.private_json(host_file, dict(sentinel='SYNTHETIC-BOUNDARY-ONLY'))
        require(H.safe_read(host_file) == dict(sentinel='SYNTHETIC-BOUNDARY-ONLY'), 'host_sentinel_missing')
        source = attack_source(dict(target=target, gateway=gateway, api_pid=api['State']['Pid'],
                                    host_file=str(host_file), api_file='/tmp/api-boundary-' + H.NONCE))
        entry = ['python', '-I', '-S', '-B', '-c', source]
        sys.path.insert(0, str(H.ROOT))
        from agent_d4_isolation.linux_engine import EngineClient, recipe, SECCOMP_PROFILE
        from agent_d4_isolation.linux_identity import KernelCollector
        from agent_d4_isolation.runtime_network import prepare_api
        engine = EngineClient(); deadline = time.monotonic_ns() + 60_000_000_000
        body = recipe(H.NONCE, receipt['image_id'], api_id); original = copy.deepcopy(body)
        body['Entrypoint'] = entry
        require({key for key in body if body[key] != original[key]} == {'Entrypoint'}, 'recipe_diff_invalid')
        # The receiver nonce label is retained unchanged; only the trusted observer
        # knows its role. Other resources have a separate boundary-only owner label.
        receipt['create_pending']['receiver'] = True; H.record_receipt(receipt)
        cid = engine._json('POST', '/containers/create', deadline, body=body, statuses=(201,))['Id']
        require(re.fullmatch('[a-f0-9]{64}', cid), 'receiver_create_unknown')
        receipt['receiver_id'] = cid
        receipt['objects'].append(dict(id=cid, role='receiver')); receipt['create_pending']['receiver'] = False; H.record_receipt(receipt)
        channel = engine.attach(cid, deadline); engine.start(cid, deadline)
        observer = OverlayObserver(engine, cid, receipt['image_id'], entry)
        collector = KernelCollector(observer, receipt['image_id'], api_id)
        binding = collector.bind(H.NONCE, cid, deadline)
        receipt['identity'] = binding.snapshot(); receipt['attack_sha256'] = hashlib.sha256(source.encode()).hexdigest()
        receipt['seccomp_sha256'] = hashlib.sha256(json.dumps(SECCOMP_PROFILE, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        receipt['lsm_profile'] = engine.inspect(cid, deadline).get('AppArmorProfile', '')
        require(type(receipt['lsm_profile']) is str and len(receipt['lsm_profile']) <= 128, 'lsm_metadata_invalid')
        chunks = channel.chunks(deadline)
        write_all(channel, b'PRE\n', deadline); pre = read_row(chunks)
        # The additional loopback listener was proven reachable and is now closed;
        # install and verify the production single-listener policy unchanged.
        manifest = dict(schema_version=1, api_container_id=api_id,
            permit=dict(image_digest=receipt['image_id'], worker_sha256=H.WORKER_SHA256,
                        receiver_uid=2001, api_uid=2002, api_port=18777))
        lease = prepare_api(engine, manifest, deadline, install=True)
        require(lease.verify(deadline) and collector.revalidate(binding, deadline) is not None, 'boundary_not_current')
        write_all(channel, b'POST\n', deadline); post = read_row(chunks)
        validate_results(pre, post)
        require(lease.verify(deadline), 'rules_changed_after_attack')
        require(H.docker('logs', api_id).stdout.decode('ascii').splitlines() == ['ready', 'other_closed', 'downstream_ok'],
                'target_or_listener_control_missing')
        require(assert_owned(target_id, receipt, 'target')['State']['Running'] is True and
                assert_owned(api_id, receipt, 'api')['State']['Running'] is True, 'control_peer_not_live')
        receipt['pre'], receipt['post'] = pre, post
        write_all(channel, b'END\n', deadline); channel.close_stdin()
        for piece in chunks: require(not piece, 'unexpected_trailing_output')
        stop_deadline = time.monotonic_ns() + 5_000_000_000
        while time.monotonic_ns() < stop_deadline:
            if binding.container_running(stop_deadline) is False and binding.tasks_remaining() == 0: break
            time.sleep(.02)
        else: raise BoundaryFailure('attack_cgroup_not_reclaimed')
        receipt['boundary_verified'] = True
    except Exception as error:
        receipt['failure_code'] = str(error) if type(error) is BoundaryFailure else 'boundary_probe_unknown'
    finally:
        close_errors = []
        if channel is not None:
            try: channel.close()
            except Exception: close_errors.append('channel_close_unknown')
        if lease is not None:
            try: lease.close()
            except Exception: close_errors.append('lease_close_unknown')
        # Receiver uses the exact production nonce label, so cleanup is deliberately
        # separate from API/target labels and never rewrites its create recipe.
        errors = []
        if receipt.get('receiver_id'):
            cid = receipt['receiver_id']
            try:
                raw = H.inspect(cid)
                require(raw['Id'] == cid and raw['Image'] == receipt['image_id'] and
                        raw['Config'].get('Labels', {}).get('org.openqms.d4.nonce') == H.NONCE,
                        'receiver_cleanup_identity_changed')
                H.docker('rm', '-f', cid); H.absent(cid)
                require(binding is None or binding.tasks_remaining() == 0, 'receiver_cgroup_unknown')
            except Exception: errors.append('receiver_cleanup_unknown')
        receipt['objects'] = [row for row in receipt['objects'] if row['role'] != 'receiver']
        cleanup_objects(receipt); receipt['cleanup_errors'] += errors + close_errors
        if binding is not None:
            try: binding.close()
            except Exception: receipt['cleanup_errors'].append('observer_close_unknown')
        try:
            left = H.docker('ps', '-aq', '--no-trunc', '--filter', 'label=' + LABEL + '=' + H.NONCE).stdout.strip()
            require(not left and not H.exact_matches(H.RECEIVER_LABEL), 'owned_resources_remain')
        except Exception: receipt['cleanup_errors'].append('absence_unknown')
        receipt['resources_cleaned'] = not receipt['cleanup_errors']
        if receipt['resources_cleaned'] and receipt['failure_code'] is None:
            try:
                info = H.ROOT.lstat()
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
                        'root_identity_changed')
                shutil.rmtree(H.ROOT)
                require(not H.ROOT.exists(), 'root_cleanup_incomplete')
            except Exception:
                receipt['resources_cleaned'] = False
                receipt['cleanup_errors'].append('root_cleanup_unknown')
        if H.ROOT.exists():
            try: H.record_receipt(receipt)
            except Exception: receipt['receipt_write_failed'] = True
        print(json.dumps(receipt, sort_keys=True), flush=True)
    require(receipt['boundary_verified'] and receipt['resources_cleaned'] and receipt['failure_code'] is None, 'boundary_not_verified')
    print('runtime_boundary_verified', flush=True)


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'image_required'); main(sys.argv[1])
    except Exception:
        print('runtime_boundary_failed', flush=True); raise SystemExit(1)
