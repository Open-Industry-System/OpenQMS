#!/usr/bin/env python3
"""Fail-closed cleanup for one explicitly registered, isolated R4b fixture.

This task-specific controller has undergone independent review and isolated
mock verification.  It never prints credentials, database URLs, container
environment, SQL, or process args.  Unresolved mounts block cleanup.
Run only after the complete T11 gates have finished.  Usage: dry-run | apply.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import subprocess
import sys
import time
from urllib.parse import quote

ROOT = Path('/private/tmp/openqms-d4-text-20261113-RUUaxY')
WORKTREE = Path('/Users/sam/Documents/Code/OpenQMS/.worktrees/agent-main-semantic-integration')
CONTAINER_ID = '706d28957c45595e0c8b3e056558ed1c8bbc55b2453345354e8ea83d9d4058ad'
OWNER = '8f168c8a4637882929447e6c'
CONTAINER = 'openqms-d4-t3-' + OWNER
VOLUME = CONTAINER + '-data'
IMAGE = 'pgvector/pgvector:pg15'
SOCKET = '/Users/sam/.docker/run/docker.sock'
PORT = 60114
SENTINEL = 'qms_d4_t3_sentinel'
CURRENT = 'qms_d4_t3_1c4e8b236518_test'
REGISTERED = {
    'resource.json': CURRENT,
    'resource.previous.1794534850897971000.json': 'qms_d4_t3_test',
    'resource.previous.1794556554820155000.json': 'qms_d4_t3_ae3ae21953ed_test',
}
SECRET_NAMES = ('credentials.json', 'postgres.env')
DRY_RECEIPT = 't11-owned-cleanup-dry-run.json'
APPLY_RECEIPT = 't11-owned-cleanup-apply.json'
ENV = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR') if key in os.environ}
STAGE = 'startup'
LAST_MOUNT_AUDIT = None


class MountOwnershipIndeterminate(RuntimeError):
    """The daemon's mount identity evidence is insufficient for cleanup."""
    def __init__(self, audit: dict):
        super().__init__('mount ownership is indeterminate')
        self.audit = audit


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def command(*args: str) -> str:
    # Never resolve a Docker daemon through mutable CLI context.  Every Docker
    # invocation in this controller addresses the same confirmed local socket.
    argv = ('docker', '--host', 'unix://' + SOCKET, *args[1:]) if args[0] == 'docker' else args
    result = subprocess.run(argv, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, check=True, timeout=30)
    return result.stdout.strip()


def private_read(name: str) -> bytes:
    require('/' not in name and name not in ('.', '..'), 'unsafe private filename')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(ROOT / name, flags)
    try:
        st = os.fstat(fd)
        require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and st.st_nlink == 1,
                'private file identity rejected')
        require(stat.S_IMODE(st.st_mode) == 0o600, 'private file mode rejected')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def exclusive_receipt(name: str, payload: dict) -> None:
    require('/' not in name, 'unsafe receipt filename')
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(payload, stream, sort_keys=True, ensure_ascii=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def registration_and_secret() -> tuple[dict, str, dict[str, str]]:
    require(hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY'),
            'required safe file operations unavailable')
    root_stat = ROOT.lstat()
    require(ROOT.resolve() == ROOT and stat.S_ISDIR(root_stat.st_mode) and root_stat.st_uid == os.getuid()
            and stat.S_IMODE(root_stat.st_mode) == 0o700, 'private root identity rejected')
    require(not any(os.environ.get(k) for k in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG',
                                                  'PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE', 'PGOPTIONS')),
            'ambient routing override present')
    hashes = {}
    current = None
    for name, db_name in REGISTERED.items():
        raw = private_read(name)
        hashes[name] = hashlib.sha256(raw).hexdigest()
        item = json.loads(raw)
        expected = {'container_id': CONTAINER_ID, 'owner_nonce': OWNER, 'container': CONTAINER,
                    'volume': VOLUME, 'image': IMAGE, 'host': '127.0.0.1', 'port': PORT,
                    'application_database': SENTINEL, 'test_database': db_name}
        require(all(item.get(key) == value for key, value in expected.items()), 'registration mismatch')
        if name == 'resource.json':
            current = item
    require(current is not None, 'missing current registration')
    credentials = json.loads(private_read('credentials.json'))
    require(set(credentials) == {'password'} and isinstance(credentials['password'], str)
            and re.fullmatch(r'[0-9a-f]{64}', credentials['password']) is not None, 'credential format rejected')
    password = credentials['password']
    expected_env = f'POSTGRES_USER=qms\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB={SENTINEL}\n'.encode()
    require(private_read('postgres.env') == expected_env, 'owned env file does not match credential')
    return current, password, hashes


def docker_endpoint() -> str:
    require(stat.S_ISSOCK(Path(SOCKET).stat().st_mode), 'Docker endpoint is not a local socket')
    daemon = json.loads(command('docker', 'info', '--format', '{{json .ID}}'))
    require(isinstance(daemon, str) and len(daemon) >= 12, 'invalid Docker daemon identity')
    return daemon


def inspect_container(*, running: bool = True) -> dict:
    fmt = ('{{json .Id}}\n{{json .Name}}\n{{json .Config.Image}}\n{{json .Config.Labels}}\n'
           '{{json .NetworkSettings.Ports}}\n{{json .Mounts}}\n{{json .State.Running}}')
    values = command('docker', 'inspect', '--format', fmt, CONTAINER_ID).splitlines()
    require(len(values) == 7, 'unexpected container inspection')
    actual_id, name, image, labels, ports, mounts, is_running = map(json.loads, values)
    require(actual_id == CONTAINER_ID and len(actual_id) == 64 and name == '/' + CONTAINER,
            'container identity mismatch')
    require(image == IMAGE and isinstance(labels, dict) and labels.get('openqms.owner') == OWNER,
            'container owner or image mismatch')
    require(is_running is running, 'container running state mismatch')
    if running:
        bindings = ports.get('5432/tcp') if isinstance(ports, dict) else None
        require(bindings == [{'HostIp': '127.0.0.1', 'HostPort': str(PORT)}], 'published endpoint mismatch')
    require(isinstance(mounts, list) and len(mounts) == 1, 'container mount count mismatch')
    mount = mounts[0]
    require(mount.get('Type') == 'volume' and mount.get('Name') == VOLUME
            and mount.get('Destination') == '/var/lib/postgresql/data' and mount.get('RW') is True,
            'container mount mismatch')
    return {'id': actual_id, 'image': image, 'labels': labels, 'ports': ports, 'mounts': mounts}


def inspect_volume(name: str = VOLUME) -> dict:
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name) is not None,
            'volume name cannot be safely inspected')
    fmt = ('{{json .Name}}\n{{json .Driver}}\n{{json .Scope}}\n{{json .Labels}}\n'
           '{{json .Options}}\n{{json .Mountpoint}}')
    values = command('docker', 'volume', 'inspect', '--format', fmt, name).splitlines()
    require(len(values) == 6, 'unexpected volume inspection')
    actual_name, driver, scope, labels, options, mountpoint = map(json.loads, values)
    require(actual_name == name and driver == 'local' and scope == 'local', 'volume identity mismatch')
    require(options in (None, {}), 'external or configured volume rejected')
    require(isinstance(mountpoint, str) and mountpoint.startswith('/')
            and posixpath.normpath(mountpoint) == mountpoint and mountpoint != '/',
            'volume mountpoint cannot be safely compared')
    if name == VOLUME:
        require(isinstance(labels, dict) and labels.get('openqms.owner') == OWNER,
                'volume owner mismatch')
    return {'name': actual_name, 'mountpoint': mountpoint}


def container_inventory() -> dict[str, str]:
    output = command('docker', 'ps', '-a', '--no-trunc', '--format', '{{.ID}} {{.Names}}')
    result = {}
    for line in output.splitlines():
        parts = line.split(' ', 1)
        require(len(parts) == 2 and re.fullmatch(r'[0-9a-f]{64}', parts[0]) is not None,
                'invalid container inventory')
        require(parts[0] not in result, 'duplicate container inventory')
        result[parts[0]] = parts[1]
    return result


def paths_intersect(first: str, second: str) -> bool:
    return (first == second or first.startswith(second.rstrip('/') + '/')
            or second.startswith(first.rstrip('/') + '/'))


def _daemon_mount_path(value: str) -> str:
    """Decode Linux mountinfo's documented escapes without consulting the host."""
    require(isinstance(value, str) and value, 'invalid mount path')
    escapes = {'040': ' ', '011': '\t', '012': '\n', '134': '\\'}
    pieces = []
    index = 0
    while index < len(value):
        if value[index] != '\\':
            pieces.append(value[index])
            index += 1
            continue
        token = value[index + 1:index + 4]
        require(token in escapes, 'unknown mountinfo escape')
        pieces.append(escapes[token])
        index += 4
    path = ''.join(pieces)
    require(path.startswith('/') and '\x00' not in path and posixpath.normpath(path) == path,
            'invalid daemon mount path')
    return path


def _linux_device_number(major: int, minor: int) -> int:
    # Linux dev_t encoding; this controller may run on a non-Linux host where
    # os.makedev uses a different platform encoding.
    require(0 <= major <= 0xffffffff and 0 <= minor <= 0xffffffff, 'invalid device number')
    return ((major & 0xfff) << 8) | ((major & ~0xfff) << 32) | (minor & 0xff) | ((minor & ~0xff) << 12)


def diagnose_daemon_mount_relation(mountinfo_text: str, stat_text: str, source_mountpoint: str,
                                   target_mountpoint: str, *, evidence_binding: dict,
                                   expected_binding: dict) -> dict:
    """Interpret supplied probe data for diagnostics only, never for deletion.

    Binding labels are compared but not independently authenticated.  There is
    no live collector in this controller: even matching labels or a positive
    conclusion cannot change a bind's cleanup classification or READY state.
    """
    def result(relation: str, reason: str) -> dict:
        return {'relation': relation, 'reason': reason, 'authorization_eligible': False}

    try:
        binding_keys = {'daemon_id', 'probe_id', 'volume_name', 'source_ref', 'capture_id'}
        require(isinstance(evidence_binding, dict) and isinstance(expected_binding, dict)
                and set(evidence_binding) == binding_keys and evidence_binding == expected_binding,
                'capture binding mismatch')
        require(all(isinstance(value, str) and 0 < len(value) <= 256 for value in evidence_binding.values())
                and re.fullmatch(r'[0-9a-f]{64}', evidence_binding['probe_id']) is not None
                and evidence_binding['volume_name'] == VOLUME, 'invalid capture binding')
        require(isinstance(mountinfo_text, str) and len(mountinfo_text) <= 2 * 1024 * 1024
                and isinstance(stat_text, str) and len(stat_text) <= 128 * 1024, 'invalid evidence size')
        source_mountpoint = _daemon_mount_path(source_mountpoint)
        target_mountpoint = _daemon_mount_path(target_mountpoint)
        entries = []
        seen_ids = set()
        for line in mountinfo_text.splitlines():
            left, separator, right = line.partition(' - ')
            fields, tail = left.split(), right.split()
            require(bool(separator) and len(fields) >= 6 and len(tail) >= 3,
                    'invalid mountinfo line')
            require(fields[0].isdigit() and fields[1].isdigit() and fields[0] not in seen_ids,
                    'invalid mountinfo identity')
            seen_ids.add(fields[0])
            device = re.fullmatch(r'(\d+):(\d+)', fields[2])
            require(device is not None, 'invalid mountinfo device')
            entries.append({'device': (int(device.group(1)), int(device.group(2))),
                            'root': _daemon_mount_path(fields[3]),
                            'mountpoint': _daemon_mount_path(fields[4]), 'filesystem': tail[0]})
        require(entries, 'empty mountinfo')
        stats = {}
        for line in stat_text.splitlines():
            fields = line.rsplit(None, 3)
            require(len(fields) == 4, 'invalid stat line')
            path, device, inode, mode = fields
            require(path.startswith('/') and '\x00' not in path and posixpath.normpath(path) == path
                    and device.isdigit() and inode.isdigit() and re.fullmatch(r'[0-9a-fA-F]+', mode),
                    'invalid stat fields')
            require(path not in stats and int(inode) > 0 and (int(mode, 16) & 0o170000) == 0o040000,
                    'ambiguous or non-directory stat')
            stats[path] = int(device)
        source = [item for item in entries if item['mountpoint'] == source_mountpoint]
        target = [item for item in entries if item['mountpoint'] == target_mountpoint]
        require(len(source) == len(target) == 1, 'missing or stacked probe mount')
        source, target = source[0], target[0]

        def reliable(item: dict) -> bool:
            return (item['filesystem'] == 'ext4'
                    and stats.get(item['mountpoint']) == _linux_device_number(*item['device']))

        if (not reliable(source) or not reliable(target) or source['device'] != target['device']
                or source['filesystem'] != target['filesystem']):
            return result('INDETERMINATE', 'filesystem_or_device_unverified')
        nested = [item for item in entries if item is not source and item is not target
                  and (item['mountpoint'].startswith(source_mountpoint.rstrip('/') + '/')
                       or item['mountpoint'].startswith(target_mountpoint.rstrip('/') + '/'))]
        for item in nested:
            if (not reliable(item) or item['device'] != source['device']
                    or item['filesystem'] != source['filesystem']):
                return result('INDETERMINATE', 'nested_mount_unverified')
        if paths_intersect(source['root'], target['root']) or paths_intersect(source_mountpoint, target_mountpoint):
            return result('RELATED', 'same_device_overlapping_root_or_mount')
        for item in nested:
            opposing = target['root'] if item['mountpoint'].startswith(source_mountpoint.rstrip('/') + '/') else source['root']
            if paths_intersect(item['root'], opposing):
                return result('RELATED', 'verified_nested_alias')
        if nested:
            return result('INDETERMINATE', 'nested_mount_present')
        return result('CONFIRMED_UNRELATED', 'same_verified_device_disjoint_roots_no_nested_mount')
    except (KeyError, TypeError, ValueError, OverflowError, RuntimeError):
        return result('INDETERMINATE', 'invalid_or_unmatched_diagnostic_evidence')


def attach_mount_diagnostic(audit: dict, container_id: str, source: str, diagnostic: dict) -> dict:
    """Return a diagnostic annotation without changing any cleanup decision."""
    require(isinstance(diagnostic, dict) and diagnostic.get('authorization_eligible') is False
            and diagnostic.get('relation') in ('RELATED', 'CONFIRMED_UNRELATED', 'INDETERMINATE'),
            'invalid diagnostic annotation')
    copied = json.loads(json.dumps(audit))
    references = copied.get('references') if isinstance(copied, dict) else None
    require(isinstance(references, list), 'invalid mount audit')
    matches = [item for item in references if isinstance(item, dict) and item.get('type') == 'bind'
               and item.get('container_id') == container_id and item.get('source') == source
               and item.get('classification') == 'indeterminate']
    require(len(matches) == 1, 'ambiguous bind diagnostic target')
    matches[0]['diagnostic'] = json.loads(json.dumps(diagnostic))
    return copied


def volume_consumers(inventory: dict[str, str], mountpoint: str) -> set[str]:
    global LAST_MOUNT_AUDIT
    # A failed fresh enumeration must never report a stale prior inventory.
    LAST_MOUNT_AUDIT = None
    consumers = set()
    audit = {'containers_inspected': 0, 'counts': {'related': 0, 'excluded': 0, 'indeterminate': 0},
             'types': {}, 'references': []}
    for ident in sorted(inventory):
        mounts = json.loads(command('docker', 'inspect', '--format', '{{json .Mounts}}', ident))
        require(isinstance(mounts, list), 'invalid container mounts')
        audit['containers_inspected'] += 1
        for item in mounts:
            kind, source = item.get('Type'), item.get('Source')
            category = kind if kind in ('volume', 'bind') else 'other'
            classification, reason = 'indeterminate', 'mount_identity_unverified'
            if kind == 'bind':
                # Mounts.Source and Mountpoint are daemon VM paths.  Host path
                # resolution, existence, and lexical (non-)intersection cannot
                # establish the daemon mount identity.  No daemon canonical or
                # mount-ID evidence is available in this controller.
                reason = 'daemon_bind_identity_unverified'
            elif (kind == 'volume' and isinstance(source, str) and source.startswith('/')
                  and posixpath.normpath(source) == source):
                other_name = item.get('Name')
                try:
                    require(isinstance(other_name, str) and other_name, 'unnamed volume mount')
                    other = inspect_volume(other_name)
                    require(other['mountpoint'] == source, 'volume source mismatch')
                    if other_name == VOLUME:
                        require(source == mountpoint, 'registered volume mountpoint mismatch')
                        classification, reason = 'related', 'exact_registered_named_volume'
                    elif not paths_intersect(source, mountpoint):
                        # Distinct daemon-managed named volumes are distinguished
                        # by Docker name after local driver/options verification;
                        # path inequality alone is never used to classify bind mounts.
                        classification, reason = 'excluded', 'different_verified_named_volume'
                    else:
                        reason = 'named_volume_mountpoints_overlap'
                except Exception:
                    reason = 'named_volume_identity_unverified'
            audit['counts'][classification] += 1
            per_type = audit['types'].setdefault(category, {'related': 0, 'excluded': 0, 'indeterminate': 0})
            per_type[classification] += 1
            audit['references'].append({'container_id': ident, 'type': category, 'name': item.get('Name'),
                                        'source': source, 'classification': classification, 'reason': reason})
            if classification == 'related':
                consumers.add(ident)
    LAST_MOUNT_AUDIT = audit
    if audit['counts']['indeterminate']:
        raise MountOwnershipIndeterminate(audit)
    return consumers


def verify_resources_present(expected_daemon: str) -> str:
    require(docker_endpoint() == expected_daemon, 'Docker daemon changed')
    container = inspect_container()
    volume = inspect_volume()
    require(container['mounts'][0].get('Source') == volume['mountpoint'], 'owned volume source mismatch')
    inventory = container_inventory()
    require(inventory.get(CONTAINER_ID) == CONTAINER, 'registered container not enumerated')
    require(volume_consumers(inventory, volume['mountpoint']) == {CONTAINER_ID}, 'volume is not exclusively consumed')
    volumes = command('docker', 'volume', 'ls', '--format', '{{.Name}}').splitlines()
    require(volumes.count(VOLUME) == 1, 'registered volume not uniquely enumerated')
    require(docker_endpoint() == expected_daemon, 'Docker daemon changed during inspection')
    return volume['mountpoint']


def process_inventory() -> None:
    # Require successful full enumeration; do not publish argv, which may contain secrets.
    output = command('ps', '-axo', 'uid=,pid=,ppid=,command=')
    processes = {}
    for line in output.splitlines():
        fields = line.strip().split(None, 3)
        require(len(fields) == 4, 'invalid process inventory')
        uid, pid, parent = map(int, fields[:3])
        processes[pid] = (uid, parent, fields[3])
    own = os.getpid()
    ancestors = {own}
    parent = processes.get(own, (None, 0, ''))[1]
    while parent and parent not in ancestors:
        ancestors.add(parent)
        parent = processes.get(parent, (None, 0, ''))[1]
    forbidden_ancestor_markers = ('pytest', 'capa_outcome_runner.py', 'readonly_d4_text_receiver.py',
                                  'readonly_8d_plugin.py', 'make check', 'vitest', 'playwright')
    for pid in ancestors - {own}:
        argv = processes.get(pid, (None, None, ''))[2]
        require(not any(marker in argv for marker in forbidden_ancestor_markers),
                'cleanup was launched by an active task process')
    markers = (str(WORKTREE), str(ROOT), 'readonly_d4_text_receiver.py',
               'readonly_8d_plugin.py', 'capa_outcome_runner.py')
    owned = {pid for pid, (uid, _, argv) in processes.items()
             if uid == os.getuid() and pid not in ancestors and any(x in argv for x in markers)}
    changed = True
    while changed:
        children = {pid for pid, (uid, ppid, _) in processes.items()
                    if uid == os.getuid() and pid not in ancestors and ppid in owned}
        changed = not children.issubset(owned)
        owned.update(children)
    require(not owned, 'task process still running')
    # An executable launched with a relative path may omit the worktree in argv.
    # Inspect cwd of every same-UID non-ancestor process; uncertainty blocks cleanup.
    for pid, (uid, _, _) in processes.items():
        if uid != os.getuid() or pid in ancestors:
            continue
        try:
            cwd_output = command('lsof', '-nP', '-a', '-p', str(pid), '-d', 'cwd', '-Fn')
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            raise RuntimeError('cannot inspect live process cwd') from None
        paths = [line[1:] for line in cwd_output.splitlines() if line.startswith('n')]
        require(len(paths) == 1, 'ambiguous process cwd')
        resolved = Path(paths[0]).resolve()
        require(not resolved.is_relative_to(WORKTREE) and not resolved.is_relative_to(ROOT),
                'task process cwd still active')


def verify_database(registration: dict, password: str) -> dict:
    # The existing project verifier checks the exact registered endpoint and owner.
    sys.path.insert(0, str(WORKTREE / 'backend'))
    from tests.ci import owned_resources
    import psycopg
    url = f"postgresql+asyncpg://qms:{quote(password, safe='')}@127.0.0.1:{PORT}/{CURRENT}"
    source = dict(ENV, TEST_DATABASE_URL=url, DATABASE_URL=url,
                  OPENQMS_TEST_RESOURCE_FILE=str(ROOT / 'resource.json'), PG15_CONTAINER=CONTAINER_ID)
    # The project verifier normally invokes bare `docker inspect`, which would
    # follow a mutable context.  Supply the same verifier with facts obtained by
    # this controller's explicit local-socket inspector for this private process.
    original_inspector = owned_resources.inspect_container
    def socket_inspector(name: str) -> dict:
        require(name == CONTAINER, 'verifier requested an unknown container')
        inspected = inspect_container()
        return {key: inspected[key] for key in ('id', 'image', 'labels', 'ports')}
    try:
        owned_resources.inspect_container = socket_inspector
        target = owned_resources.verify_owned_instance(source)
    finally:
        owned_resources.inspect_container = original_inspector
    require(target.container_id == CONTAINER_ID and target.host == '127.0.0.1'
            and target.port == PORT and target.database == CURRENT, 'verified database mismatch')
    known = set(REGISTERED.values())
    allowed = known | {SENTINEL, 'postgres', 'template0', 'template1'}
    with psycopg.connect(host='127.0.0.1', hostaddr='127.0.0.1', port=PORT,
                         user='qms', password=password, dbname='postgres') as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT current_database(), current_user, rolsuper FROM pg_roles WHERE rolname=current_user')
            require(cur.fetchone() == ('postgres', 'qms', True), 'database administrator identity mismatch')
            cur.execute("SELECT datname FROM pg_database ORDER BY datname")
            names = {row[0] for row in cur.fetchall()}
            require(names == allowed, 'database inventory contains absent or unknown database')
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid <> pg_backend_pid()")
            require(cur.fetchone()[0] == 0, 'database client still connected')
    # Each connection is sequential and read-only; sentinel data are never opened.
    tenant_counts = {}
    for database in sorted(known):
        with psycopg.connect(host='127.0.0.1', hostaddr='127.0.0.1', port=PORT,
                             user='qms', password=password, dbname=database,
                             options='-c default_transaction_read_only=on') as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database(), current_user')
                require(cur.fetchone() == (database, 'qms'), 'test database identity mismatch')
                cur.execute('SELECT count(*) FROM public.tenants')
                tenant_counts[database] = cur.fetchone()[0]
                require(tenant_counts[database] == 0, 'fixture tenant remains in a registered database')
    return {'registered_test_databases': sorted(known), 'sentinel_database': SENTINEL,
            'tenant_counts': tenant_counts, 'other_clients': 0, 'migration_databases': 0}


def verify_all() -> dict:
    global STAGE, LAST_MOUNT_AUDIT
    STAGE = 'registration'
    registration, password, hashes = registration_and_secret()
    STAGE = 'resource inspection'
    daemon = docker_endpoint()
    LAST_MOUNT_AUDIT = None
    mountpoint = verify_resources_present(daemon)
    require(LAST_MOUNT_AUDIT is not None, 'mount inventory was not recorded')
    first_mount_audit = json.loads(json.dumps(LAST_MOUNT_AUDIT))
    STAGE = 'process inspection'
    process_inventory()
    STAGE = 'database inspection'
    database = verify_database(registration, password)
    # Fresh enumeration after SQL inspection narrows the time-of-check window.
    STAGE = 'resource reinspection'
    LAST_MOUNT_AUDIT = None
    require(verify_resources_present(daemon) == mountpoint, 'volume mountpoint changed')
    require(LAST_MOUNT_AUDIT == first_mount_audit, 'mount inventory changed during inspection')
    process_inventory()
    # Repeat the client/tenant inventory immediately before permitting stop.
    require(verify_database(registration, password) == database, 'database inventory changed')
    return {'container_id': CONTAINER_ID, 'container': CONTAINER, 'owner_nonce': OWNER,
            'volume': VOLUME, 'host': '127.0.0.1', 'port': PORT,
            'docker_socket': 'unix://' + SOCKET, 'docker_daemon_id': daemon,
            'volume_mountpoint': mountpoint,
            'mount_audit': first_mount_audit,
            'registration_sha256': hashes, 'database': database,
            'intended_secret_files': list(SECRET_NAMES)}


def remove_owned_secrets() -> None:
    # Revalidate contents, identities and modes after resource deletion.
    registration_and_secret()
    directory_fd = os.open(ROOT, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        for name in SECRET_NAMES:
            st = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            require(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid()
                    and st.st_nlink == 1 and stat.S_IMODE(st.st_mode) == 0o600,
                    'secret file identity changed')
            os.unlink(name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def main() -> None:
    global STAGE, LAST_MOUNT_AUDIT
    require(len(sys.argv) == 2 and sys.argv[1] in ('dry-run', 'apply'), 'mode must be dry-run or apply')
    mode = sys.argv[1]
    require(not Path(ROOT / APPLY_RECEIPT).exists(), 'apply receipt already exists')
    if mode == 'apply':
        dry = json.loads(private_read(DRY_RECEIPT))
        require(dry.get('status') == 'READY' and dry.get('container_id') == CONTAINER_ID
                and dry.get('owner_nonce') == OWNER and dry.get('volume') == VOLUME,
                'verified dry-run receipt required')
    facts = verify_all()
    if mode == 'dry-run':
        STAGE = 'dry-run receipt'
        exclusive_receipt(DRY_RECEIPT, {'status': 'READY', 'timestamp_utc': int(time.time()), **facts})
        print(json.dumps({'status': 'READY', 'receipt': str(ROOT / DRY_RECEIPT)}))
        return
    require(dry.get('registration_sha256') == facts['registration_sha256']
            and dry.get('database') == facts['database'] and dry.get('host') == facts['host']
            and dry.get('port') == facts['port'] and dry.get('container') == facts['container']
            and dry.get('docker_socket') == facts['docker_socket']
            and dry.get('docker_daemon_id') == facts['docker_daemon_id']
            and dry.get('volume_mountpoint') == facts['volume_mountpoint']
            and dry.get('mount_audit') == facts['mount_audit'],
            'resource facts changed after dry-run')
    STAGE = 'stop container'
    LAST_MOUNT_AUDIT = None
    require(docker_endpoint() == facts['docker_daemon_id'], 'Docker daemon changed before stop')
    command('docker', 'stop', '--time', '10', CONTAINER_ID)
    # A successful inspection and a successful complete inventory are required,
    # not a failed inspect interpreted as absence.  Stop keeps mount identity.
    STAGE = 'stopped container reinspection'
    LAST_MOUNT_AUDIT = None
    require(docker_endpoint() == facts['docker_daemon_id'], 'Docker daemon changed after stop')
    inspect_container(running=False)
    require(inspect_volume()['mountpoint'] == facts['volume_mountpoint'], 'volume mountpoint changed after stop')
    before = container_inventory()
    require(before.get(CONTAINER_ID) == CONTAINER
            and volume_consumers(before, facts['volume_mountpoint']) == {CONTAINER_ID},
            'container or volume ownership changed after stop')
    STAGE = 'remove container'
    LAST_MOUNT_AUDIT = None
    require(docker_endpoint() == facts['docker_daemon_id'], 'Docker daemon changed before container removal')
    command('docker', 'rm', CONTAINER_ID)
    STAGE = 'confirm container absence'
    LAST_MOUNT_AUDIT = None
    after = container_inventory()
    require(CONTAINER_ID not in after and CONTAINER not in after.values(), 'container still present')
    require(not volume_consumers(after, facts['volume_mountpoint']), 'another volume consumer exists')
    STAGE = 'remove volume'
    LAST_MOUNT_AUDIT = None
    require(docker_endpoint() == facts['docker_daemon_id'], 'Docker daemon changed before volume removal')
    require(inspect_volume()['mountpoint'] == facts['volume_mountpoint'], 'volume mountpoint changed before removal')
    command('docker', 'volume', 'rm', VOLUME)
    STAGE = 'confirm resource absence'
    LAST_MOUNT_AUDIT = None
    require(docker_endpoint() == facts['docker_daemon_id'], 'Docker daemon changed during removal')
    final_containers = container_inventory()
    final_volumes = command('docker', 'volume', 'ls', '--format', '{{.Name}}').splitlines()
    require(CONTAINER_ID not in final_containers and CONTAINER not in final_containers.values()
            and VOLUME not in final_volumes, 'resource absence not confirmed')
    STAGE = 'remove exact private credentials'
    remove_owned_secrets()
    STAGE = 'apply receipt'
    exclusive_receipt(APPLY_RECEIPT, {'status': 'REMOVED', 'timestamp_utc': int(time.time()),
        **facts, 'container_absent': True, 'volume_absent': True,
        'removed_secret_files': list(SECRET_NAMES), 'preserved': 'registration, logs, XML, manifests, images and other resources'})
    print(json.dumps({'status': 'REMOVED', 'receipt': str(ROOT / APPLY_RECEIPT)}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        # Never echo subprocess output, SQL, arguments, URLs or credentials.
        failure = {'status': 'INDETERMINATE' if isinstance(exc, MountOwnershipIndeterminate) else 'FAILED_CLOSED',
                   'stage': STAGE, 'timestamp_utc': int(time.time()),
                   'container_id': CONTAINER_ID, 'volume': VOLUME,
                   'mode': sys.argv[1] if len(sys.argv) == 2 and sys.argv[1] in ('dry-run', 'apply') else 'invalid'}
        audit = exc.audit if isinstance(exc, MountOwnershipIndeterminate) else LAST_MOUNT_AUDIT
        if audit is not None:
            # Summary contains only counts/types; daemon path details remain in
            # the private receipt and are never sent to stdout/stderr.
            failure['mount_summary'] = {key: audit[key] for key in ('containers_inspected', 'counts', 'types')}
        try:
            root_stat = ROOT.lstat()
            require(hasattr(os, 'O_NOFOLLOW') and ROOT.resolve() == ROOT
                    and stat.S_ISDIR(root_stat.st_mode) and root_stat.st_uid == os.getuid()
                    and stat.S_IMODE(root_stat.st_mode) == 0o700, 'unsafe receipt root')
            receipt = f't11-owned-cleanup-failure-{time.time_ns()}.json'
            private_failure = dict(failure)
            if audit is not None:
                private_failure['mount_audit'] = audit
            exclusive_receipt(receipt, private_failure)
            failure['receipt'] = str(ROOT / receipt)
        except BaseException:
            # An unsafe or unwritable evidence directory is itself fail closed.
            failure['receipt'] = 'unavailable'
        print(json.dumps(failure), file=sys.stderr)
        sys.exit(1)
