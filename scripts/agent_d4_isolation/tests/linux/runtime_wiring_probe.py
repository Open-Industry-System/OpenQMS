"""Trusted root-only wire smoke; no DB or platform authority; never collected.

Constants PACKAGE_B64, PACKAGE_SHA256 and WIRE_FIXTURE_SOURCE are injected by the
explicit opt-in test. This file does not change the immutable receiver image.
Only the root controller launches that receiver. Failure never counts as a pass.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import time

WORKER_SHA256 = '3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21'
RECEIVER_LABEL = 'org.openqms.d4.nonce'
SMOKE_LABEL = 'org.openqms.d4.smoke.nonce'
ROLE_LABEL = 'org.openqms.d4.smoke.role'
NONCE = secrets.token_hex(32)
ROOT = Path('/run') / ('oqms-d4-' + NONCE)
UNITS = tuple('openqms-d4-' + role + '-' + NONCE + '.service' for role in ('controller', 'watchdog'))


class ProbeFailure(Exception):
    """Fixed error codes only; no argv, HTTP bytes or environment diagnostics."""


def require(condition, code):
    if not condition:
        raise ProbeFailure(code)


def run(argv, *, timeout=10, check=True):
    try:
        value = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                               timeout=timeout, check=False, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})
    except (OSError, TimeoutError, subprocess.TimeoutExpired):
        raise ProbeFailure('management_command_unknown') from None
    require(len(value.stdout) <= 256 * 1024 and len(value.stderr) <= 256 * 1024, 'management_output_limit')
    if check:
        require(value.returncode == 0, 'management_command_failed')
    return value


def docker(*arguments, timeout=10, check=True):
    return run(['/usr/bin/docker', *arguments], timeout=timeout, check=check)


def inspect(identity):
    value = json.loads(docker('inspect', identity).stdout)
    require(type(value) is list and len(value) == 1 and value[0]['Id'] == identity, 'inspect_identity_mismatch')
    return value[0]


def private_json(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            require(count > 0, 'private_write_failed')
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)



def record_receipt(value):
    """Durable resource-only ledger, retained if create/cleanup is unresolved."""
    temporary = ROOT / ('.probe-receipt-' + secrets.token_hex(12))
    private_json(temporary, value)
    os.replace(temporary, ROOT / 'probe-receipt.json')
    directory = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def unpack_package():
    payload = base64.b64decode(PACKAGE_B64, validate=True)
    require(len(payload) <= 2 * 1024 * 1024 and hashlib.sha256(payload).hexdigest() == PACKAGE_SHA256,
            'package_digest_mismatch')
    ROOT.mkdir(mode=0o700)
    package = ROOT / 'agent_d4_isolation'
    package.mkdir(mode=0o755)
    (package / 'deploy').mkdir(mode=0o755)
    package.chmod(0o755)
    (package / 'deploy').chmod(0o755)
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:') as archive:
        for member in archive:
            name = member.name
            valid = re.fullmatch(r'agent_d4_isolation/[a-z_][a-z_0-9]*\.py', name)
            require(bool(valid) or name == 'agent_d4_isolation/deploy/runtime_entry.py', 'package_member_invalid')
            require(member.isfile() and name not in seen and member.size <= 256 * 1024, 'package_member_invalid')
            seen.add(name)
            source = archive.extractfile(member)
            require(source is not None, 'package_member_invalid')
            content = source.read(member.size + 1)
            require(len(content) == member.size, 'package_member_invalid')
            descriptor = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
            try:
                view = memoryview(content)
                while view:
                    count = os.write(descriptor, view)
                    require(count > 0, 'package_write_failed')
                    view = view[count:]
            finally:
                os.close(descriptor)
    require('agent_d4_isolation/__init__.py' in seen and
            'agent_d4_isolation/deploy/runtime_entry.py' in seen, 'package_entry_missing')
    (ROOT / 'private').mkdir(mode=0o700)


def owned_wire_source():
    # Bound request reads are parsed only to verify six fixed route/method codes;
    # request bodies, headers and response data are never printed or persisted.
    return WIRE_FIXTURE_SOURCE + r'''
import time
expected=[('POST','claim'),('GET','capabilities'),('POST','messages/claim'),
          ('GET','capa/d4/root-cause-text'),('POST','messages/ack'),('POST','finish')]
listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
listener.bind(('127.0.0.1',18777));listener.listen(1);listener.settimeout(45)
print('ready',flush=True)
for index,(method,path) in enumerate(expected):
 connection,_=listener.accept()
 with connection:
  connection.settimeout(5)
  request=bytearray()
  while b'\r\n\r\n' not in request:
   piece=connection.recv(4096)
   if not piece or len(request)+len(piece)>65536:raise SystemExit(2)
   request.extend(piece)
  head,body=bytes(request).split(b'\r\n\r\n',1)
  if head.split(b'\r\n',1)[0]!=(method+' /api/agent/runtime/'+path+' HTTP/1.1').encode():raise SystemExit(3)
  lengths=[line.split(b':',1)[1].strip() for line in head.split(b'\r\n')[1:] if line.lower().startswith(b'content-length:')]
  if len(lengths)!=1 or not lengths[0].isdigit() or int(lengths[0])>65536:raise SystemExit(4)
  while len(body)<int(lengths[0]):
   piece=connection.recv(min(4096,int(lengths[0])-len(body)))
   if not piece:raise SystemExit(5)
   body+=piece
  print('seen_'+str(index),flush=True)
  if index==0:time.sleep(3) # Allow the trusted test observer to pin this live cgroup.
  connection.sendall(reply(responses()[index]))
# Keep the one trusted API listener alive until exact owner cleanup. The receiver
# must not lose its API identity as an artifact of the test fixture ending.
while True:time.sleep(1)
'''


def exact_matches(label):
    out = docker('ps', '-aq', '--no-trunc', '--filter', 'label=' + label + '=' + NONCE).stdout.decode('ascii')
    values = tuple(line for line in out.splitlines() if line)
    require(all(re.fullmatch('[a-f0-9]{64}', value) for value in values), 'enumeration_invalid')
    return values


def assert_owned(identity, image_id, role):
    raw = inspect(identity)
    labels = raw['Config'].get('Labels') or {}
    require(raw['Image'] == image_id, 'cleanup_image_mismatch')
    if role == 'api':
        require(labels.get(SMOKE_LABEL) == NONCE and labels.get(ROLE_LABEL) == 'api', 'cleanup_owner_mismatch')
    else:
        require(labels.get(RECEIVER_LABEL) == NONCE, 'cleanup_owner_mismatch')
    return raw


def absent(identity):
    result = docker('inspect', identity, check=False)
    require(result.returncode != 0 and any(code in result.stderr.lower() for code in
            (b'no such object', b'no such container')), 'cleanup_absence_unverified')


def unit_view(unit):
    result = run(['/usr/bin/systemctl', 'show', unit,
                  '--property=LoadState,ActiveState,SubState,Result,ExecMainStatus'], check=False)
    facts = {}
    for line in result.stdout.decode('ascii').splitlines():
        key, sep, value = line.partition('=')
        require(sep and key not in facts, 'unit_metadata_invalid')
        facts[key] = value
    require('ActiveState' in facts and 'LoadState' in facts, 'unit_metadata_missing')
    return facts


def safe_read(path):
    if not path.exists():
        return None
    require(path.stat().st_size <= 32768 and not path.is_symlink(), 'state_file_invalid')
    return json.loads(path.read_text())



def summarize_runtime(receipt, prefix=''):
    """Only small fixed infrastructure fields; never config or raw snapshot."""
    records = (
        ('state', ROOT / 'state' / (NONCE + '.json'),
         ('phase', 'revision', 'invalidated', 'deadline_ns', 'first_stdin_ns',
          'receiver_id', 'create_converged', 'watchdog_bound_verified',
          'controller_invocation_id', 'watchdog_invocation_id')),
        ('journal', ROOT / 'state/journal' / (NONCE + '.json'),
         ('state', 'revision', 'doubted', 'closed_by', 'container_id', 'deadline_ns')))
    for name, path, keys in records:
        try:
            value = safe_read(path)
            receipt[prefix + name + '_summary'] = ({key: value.get(key) for key in keys}
                                                    if type(value) is dict else None)
        except Exception:
            receipt[prefix + name + '_summary'] = 'unreadable'


def main(image_tag):
    require(os.geteuid() == 0, 'root_required')
    require(type(image_tag) is str and image_tag and not image_tag.startswith('-'), 'image_required')
    image_id = api_id = receiver_id = binding = None
    api_create_pending = receiver_create_unknown = False
    clean = False
    smoke = False
    failure = None
    safe_receipt = {'nonce': NONCE, 'root': str(ROOT), 'units': list(UNITS), 'bundle_sha256': PACKAGE_SHA256}
    try:
        safe_receipt['stage'] = 'package'
        unpack_package()
        record_receipt(safe_receipt)
        image = json.loads(docker('image', 'inspect', image_tag).stdout)
        require(type(image) is list and len(image) == 1, 'image_inspect_invalid')
        image_id = image[0]['Id']
        require(re.fullmatch('sha256:[a-f0-9]{64}', image_id), 'image_id_invalid')
        safe_receipt['image_id'] = image_id
        # API fixture also uses the fixed owned image, no download/build/mount/DB.
        safe_receipt['stage'] = 'api_create'
        api_create_pending = True
        safe_receipt['api_create_pending'] = True
        record_receipt(safe_receipt)
        created = docker('create', '--pull=never', '--name', 'oqms-d4-wire-' + NONCE,
                         '--label', SMOKE_LABEL + '=' + NONCE, '--label', ROLE_LABEL + '=api',
                         '--network', 'bridge', '--user', '2002:2002', '--cap-drop', 'ALL',
                         '--security-opt', 'no-new-privileges', '--read-only',
                         '--memory', '128m', '--memory-swap', '128m', '--pids-limit', '16', '--cpus', '1',
                         '--ulimit', 'core=0:0', '--log-driver', 'json-file',
                         '--log-opt', 'max-size=16k', '--log-opt', 'max-file=1',
                         '--entrypoint', 'python', image_id, '-I', '-S', '-B', '-u', '-c', owned_wire_source())
        api_id = created.stdout.decode('ascii').strip()
        require(re.fullmatch('[a-f0-9]{64}', api_id), 'api_create_unknown')
        assert_owned(api_id, image_id, 'api')
        api_create_pending = False
        safe_receipt['api_id'] = api_id
        safe_receipt['api_create_pending'] = False
        record_receipt(safe_receipt)
        safe_receipt['stage'] = 'api_listener'
        docker('start', api_id)
        ready_deadline = time.monotonic() + 5
        while time.monotonic() < ready_deadline:
            if docker('logs', api_id).stdout.decode('ascii').splitlines() == ['ready']:
                break
            time.sleep(.05)
        else:
            raise ProbeFailure('api_listener_not_ready')
        fixture_namespace = {}
        exec(compile(WIRE_FIXTURE_SOURCE, '<owned-wire-fixture>', 'exec'), fixture_namespace)
        config = fixture_namespace['config']('http://127.0.0.1:18777')
        config['request_key'] = NONCE
        private_json(ROOT / 'private/config.json', config)
        private_json(ROOT / 'deployment.json', {
            'schema_version': 1, 'api_container_id': api_id,
            'permit': dict(image_digest=image_id, worker_sha256=WORKER_SHA256,
                           receiver_uid=2001, api_uid=2002, api_port=18777)})
        sys.path.insert(0, str(ROOT))
        from agent_d4_isolation.linux_engine import EngineClient
        from agent_d4_isolation.linux_identity import KernelCollector
        engine = EngineClient()
        collector = KernelCollector(engine, image_id, api_id)
        entry = ROOT / 'agent_d4_isolation/deploy/runtime_entry.py'
        safe_receipt['stage'] = 'runtime_launch'
        started = time.monotonic()
        finish_deadline = started + 40
        launched = run(['/usr/bin/python3', '-I', '-S', '-B', str(entry), 'launch', '--nonce', NONCE],
                       timeout=min(15, finish_deadline - time.monotonic()), check=False)
        require(launched.stdout.strip() in (b'isolation_unknown', b'{"status":"isolation_unknown"}'),
                'launch_output_invalid')
        safe_receipt['stage'] = 'runtime_observe'
        state_path = ROOT / 'state' / (NONCE + '.json')
        journal_path = ROOT / 'state/journal' / (NONCE + '.json')
        while time.monotonic() < finish_deadline:
            state, journal = safe_read(state_path), safe_read(journal_path)
            if journal and journal.get('container_id'):
                receiver_id = journal['container_id']
                require(re.fullmatch('[a-f0-9]{64}', receiver_id), 'receiver_identity_invalid')
                assert_owned(receiver_id, image_id, 'receiver')
                if safe_receipt.get('receiver_id') != receiver_id:
                    safe_receipt['receiver_id'] = receiver_id
                    record_receipt(safe_receipt)
            if binding is None and state and state.get('snapshot') and receiver_id:
                # An independent trusted observer pins current kernel references
                # during the deliberate first-response delay, before receiver exit.
                binding = collector.bind(NONCE, receiver_id, deadline_ns=time.monotonic_ns() + 2 * 10**9)
                require(binding.snapshot() == state['snapshot'], 'observer_snapshot_mismatch')
            view = unit_view(UNITS[0])
            if view['ActiveState'] in ('inactive', 'failed'):
                break
            time.sleep(.05)
        else:
            raise ProbeFailure('controller_40s_deadline')
        state, journal = safe_read(state_path), safe_read(journal_path)
        if binding is not None:
            fact = os.fstat(binding.cgroup.fd)
            observed = dict(device=fact.st_dev, inode=fact.st_ino, nlink=fact.st_nlink,
                            tasks=binding.tasks_remaining())
            try:
                os.lseek(binding.cgroup.events_fd, 0, os.SEEK_SET)
                raw = os.read(binding.cgroup.events_fd, 1024).decode('ascii')
                observed['events'] = dict(row.split() for row in raw.splitlines())
            except OSError as error:
                observed['events_errno'] = error.errno
            safe_receipt['observer_cgroup'] = observed
        if api_id is not None:
            codes = docker('logs', api_id).stdout.decode('ascii').splitlines()
            safe_receipt['six_wire_codes_seen'] = codes == ['ready'] + ['seen_' + str(i) for i in range(6)]
        if receiver_id is not None:
            safe_receipt['receiver_running'] = inspect(receiver_id)['State']['Running']
        require(journal is not None and journal.get('state') == 'closed' and
                journal.get('closed_by') == 'reclaim_verified' and not journal.get('doubted'), 'journal_not_reclaimed')
        require(receiver_id is not None and binding is not None, 'trusted_observer_not_bound')
        receiver_facts = inspect(receiver_id)
        require(receiver_facts['State']['Running'] is False, 'receiver_still_running')
        require(config['secret'] not in json.dumps(receiver_facts), 'receiver_inspect_contains_config')
        require(binding.tasks_remaining() == 0, 'receiver_cgroup_not_empty')
        require(state['watchdog_bound_verified'] and state['first_stdin_ns'] is not None,
                'runtime_delivery_not_verified')
        require(state['first_stdin_ns'] <= journal['deadline_ns'], 'preparation_budget_exceeded')
        safe_receipt['stage'] = 'wire_and_log_assertions'
        api_lines = docker('logs', api_id).stdout.decode('ascii').splitlines()
        require(api_lines == ['ready'] + ['seen_' + str(index) for index in range(6)], 'six_routes_not_seen')
        logs = run(['/usr/bin/journalctl', '--quiet', '--no-pager', '--output=cat',
                    '--unit=' + UNITS[0], '--identifier=python3']).stdout.decode('ascii').splitlines()
        # With no user-influenced payload in the owned fixture, any extra line
        # still fails: receiver completed/count/UUID output must never escape.
        allowed = {'{"status":"isolation_exited"}', '{"status":"isolation_terminated"}', 'isolation_terminated'}
        require(logs and all(line in allowed for line in logs) and
                '{"status":"isolation_exited"}' in logs, 'controller_log_not_fixed_infrastructure')
        safe_receipt.update(journal_state='closed', closed_by='reclaim_verified',
                            six_route_codes=True, cgroup_empty=True, elapsed=round(time.monotonic() - started, 3))
        safe_receipt['stage'] = 'verified'
        smoke = True
    except Exception as error:
        failure = str(error) if type(error) is ProbeFailure else 'runtime_probe_failed'
    finally:
        summarize_runtime(safe_receipt)
        try:
            # Stop only the two exact registered units while their fixed entry
            # and state remain present. Reset only these units, never a prefix.
            if ROOT.exists():
                run(['/usr/bin/systemctl', 'stop', *UNITS], timeout=15, check=False)
                for unit in UNITS:
                    require(unit_view(unit)['ActiveState'] not in ('active', 'activating', 'deactivating'),
                            'cleanup_unit_still_active')
                run(['/usr/bin/systemctl', 'reset-failed', *UNITS], check=False)
            summarize_runtime(safe_receipt, 'post_stop_')
            journal = safe_read(ROOT / 'state/journal' / (NONCE + '.json')) if ROOT.exists() else None
            if journal:
                receiver_create_unknown = journal.get('state') in ('create_inflight', 'unresolved') or bool(journal.get('doubted'))
                if receiver_id is None and journal.get('container_id'):
                    receiver_id = journal['container_id']
                    safe_receipt['receiver_id'] = receiver_id
            known = []
            if receiver_id is not None:
                require(re.fullmatch('[a-f0-9]{64}', receiver_id), 'cleanup_receiver_identity_invalid')
                known.append((receiver_id, 'receiver'))
            if api_id is not None and re.fullmatch('[a-f0-9]{64}', api_id):
                known.append((api_id, 'api'))
            for identity, role in known:
                assert_owned(identity, image_id, role)
                docker('rm', '-f', identity)
                absent(identity)
            remaining = exact_matches(RECEIVER_LABEL) + exact_matches(SMOKE_LABEL)
            safe_receipt['remaining_container_ids'] = list(remaining)
            require(not remaining, 'cleanup_exact_nonce_objects_remain')
            require(not api_create_pending and not receiver_create_unknown, 'cleanup_create_unresolved')
            require(journal is None or journal.get('state') == 'closed', 'cleanup_intent_unresolved')
            unit_gc_deadline = time.monotonic() + 3
            while True:
                views = [unit_view(unit) for unit in UNITS]
                if all(view['LoadState'] == 'not-found' for view in views):
                    break
                require(time.monotonic() < unit_gc_deadline, 'cleanup_unit_remaining')
                time.sleep(.05)
            # /run itself and this exact root are checked; never follow a link or
            # remove any directory selected by a container or response payload.
            if ROOT.exists():
                info = ROOT.lstat()
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
                        'cleanup_root_identity_mismatch')
                shutil.rmtree(ROOT)
            require(not ROOT.exists(), 'cleanup_root_remaining')
            clean = True
        except Exception as error:
            cleanup_code = str(error) if type(error) is ProbeFailure else 'cleanup_failed'
            safe_receipt['cleanup_error'] = cleanup_code
            failure = failure or cleanup_code
        if binding is not None:
            binding.close()
        safe_receipt.update(api_create_pending=api_create_pending, receiver_create_unknown=receiver_create_unknown,
                            cleanup_verified=clean, smoke_verified=smoke)
        safe_receipt['failure_code'] = failure
        if ROOT.exists():
            try:
                record_receipt(safe_receipt)
            except Exception:
                safe_receipt['receipt_write_failed'] = True
        # Only trusted resource identities/fixed classifications are returned.
        print(json.dumps(safe_receipt, sort_keys=True), flush=True)
        if clean:
            print('cleanup_verified', flush=True)
    require(smoke and clean, failure or 'runtime_wiring_not_verified')
    print('runtime_wiring_smoke_ok', flush=True)


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'image_required')
        main(sys.argv[1])
    except Exception as error:
        code = str(error) if type(error) is ProbeFailure else 'runtime_probe_failed'
        print('runtime_wiring_failed:' + code, flush=True)
        raise SystemExit(1)
