#!/usr/bin/env python3
"""Allocate isolated D4 cells using the approved images and current preview release."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import time
from uuid import uuid4

from cleanup import command, docker_inventory, runtime_staging_path
from executor import QUEUE_ROOT
from provision import DB_SOCKET, POSTGRES_SOCKET, permitted_cells, wait_health
from runtime_launch import (
    ENTRY, HEX64, IMAGE, MANIFEST, decode, read_owned, require, trusted_directory, verify_bundle,
)
from witness import DATABASE, DOCKER, LEASE_LABEL, ROLE, ROLE_LABEL


NATIVE_SOURCE = Path('/usr/local/lib/openqms/d4-acceptance/native')
PORT = 18777
DB_ADMIN = 'd4_bootstrap'
DB_APP = 'd4_fixture'


def docker(*args, data=None, timeout=25, stage='docker_operation'):
    outcome = subprocess.run((*DOCKER, *args), input=data if data is not None else b'', env={},
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=timeout, check=False)
    require(outcome.returncode == 0 and len(outcome.stdout) <= 262144, stage)
    return outcome.stdout.decode().strip()


def write(path, data, mode=0o600):
    flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL
    with os.fdopen(os.open(path, flags, mode), 'wb') as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path, data):
    write(path, json.dumps(data, separators=(',', ':')).encode())


def image_record(image):
    require(IMAGE.fullmatch(image), 'invalid_image_id')
    rows = json.loads(docker('image', 'inspect', image, stage='pinned_image_unavailable'))
    require(len(rows) == 1 and rows[0]['Id'] == image, 'image_identity_changed')
    return rows[0]


def native_sources(directory, pin):
    require(HEX64.fullmatch(pin), 'invalid_native_manifest_pin')
    verify_bundle(directory, pin)
    raw = read_owned(directory / MANIFEST, 65536, private=True)
    entries = decode(raw)
    allowed = r'agent_d4_isolation/(?:[a-z0-9_]+\.py|deploy/runtime_entry\.py)'
    require(ENTRY in entries and all(re.fullmatch(allowed, name) for name in entries),
            'unexpected_native_runtime_file')
    sources = {name: read_owned(directory / name, 2 * 1024 * 1024) for name in entries}
    require(all(hashlib.sha256(content).hexdigest() == entries[name] for name, content in sources.items()),
            'native_source_changed')
    return raw, sources


def pg_command(container, user, *options, data=None, stage='postgres_operation'):
    return docker(
        'exec', '--interactive', '--user', user, container, '/usr/bin/env', '-i',
        'PATH=/usr/bin:/bin', 'psql', '-X', '-w', '-qAt', '-v', 'ON_ERROR_STOP=1',
        '-h', POSTGRES_SOCKET, '-d', DATABASE, *options, data=data, stage=stage,
    )


def configure_database(container, password, subnet):
    step = 'postgres_bootstrap'
    # All values inserted below are fixed identifiers, an inspected subnet, or
    # generated URL-safe tokens. SQL travels only via stdin.
    bootstrap = f"""CREATE ROLE {DB_APP} LOGIN PASSWORD '{password}';
CREATE ROLE {ROLE} LOGIN;
ALTER DATABASE {DATABASE} OWNER TO {DB_APP};
REVOKE CONNECT ON DATABASE {DATABASE} FROM PUBLIC;
GRANT CONNECT ON DATABASE {DATABASE} TO {ROLE};
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO {DB_APP}, {ROLE};
"""
    end = time.monotonic() + 90
    while time.monotonic() < end:
        # Wait for the actual entrypoint exec, rather than its temporary init
        # PostgreSQL server which also answers pg_isready during initialization.
        try:
            postgres_pid1 = docker('exec', container, 'cat', '/proc/1/comm', stage=step) == 'postgres'
            if postgres_pid1 and pg_command(container, 'postgres', '-U', DB_ADMIN, '-c', 'SELECT 1', stage=step) == '1':
                break
        except (RuntimeError, ValueError, subprocess.SubprocessError):
            pass
        time.sleep(1)
    else:
        raise ValueError('postgres_startup_timeout')
    pg_command(container, 'postgres', '-U', DB_ADMIN, '-f', '-', data=bootstrap.encode(), stage=step)

    # Local peer identity makes the bootstrap and witness roles unavailable to
    # the candidate UID even though it has a well-scoped socket mount.
    hba = (f'local all {DB_ADMIN} peer map=d4_local\n'
           f'local {DATABASE} {ROLE} peer map=d4_local\n'
           f'local {DATABASE} {DB_APP} scram-sha-256\n'
           'local all all reject\n'
           f'host {DATABASE} {DB_APP} {subnet} scram-sha-256\n'
           'host all all all reject\n').encode()
    ident = f'd4_local postgres {DB_ADMIN}\nd4_local nobody {ROLE}\n'.encode()
    for filename, content in (('pg_ident.conf', ident), ('pg_hba.conf', hba)):
        docker('exec', '--interactive', '--user', 'postgres', container, 'sh', '-ec',
               'umask 077; cat > "$PGDATA/$1.next"; mv "$PGDATA/$1.next" "$PGDATA/$1"',
               'd4-postgres-conf', filename, data=content, stage='postgres_peer_identity')
    require(pg_command(container, 'postgres', '-U', DB_ADMIN, '-c', 'SELECT pg_reload_conf()',
                       stage='postgres_reload') == 't', 'postgres_reload_failed')
    until = time.monotonic() + 10
    while time.monotonic() < until:
        try:
            result = pg_command(container, '65534:65534', '-U', ROLE, '-c',
                                "SELECT current_database() || ':' || system_identifier FROM pg_control_system()",
                                stage='postgres_witness_check')
            database, cluster = result.split(':', maxsplit=1)
            require(database == DATABASE and re.fullmatch(r'[1-9][0-9]{0,19}', cluster),
                    'postgres_witness_identity_unverified')
            return cluster
        except (RuntimeError, ValueError, subprocess.SubprocessError):
            time.sleep(0.3)
    raise ValueError('postgres_witness_timeout')


def allocate_case(lease, kind, allocation, prefix, network, subnet, db_image, backend, pg_user):
    deliver = kind == 'deliver'
    db_name, api_name = (f'{prefix}-{kind}-{role}' for role in ('postgres', 'api'))
    data_volume = db_name + '-data'
    owner = f'{LEASE_LABEL}={lease}'
    require(docker('volume', 'create', '--label', owner, data_volume, stage='postgres_volume') == data_volume,
            'unexpected_volume_identity')

    password = secrets.token_urlsafe(36)
    env_path = allocation / (kind + '-postgres.env')
    write(env_path, (f'POSTGRES_USER={DB_ADMIN}\nPOSTGRES_PASSWORD={secrets.token_urlsafe(36)}\n'
                     f'POSTGRES_DB={DATABASE}\n'
                     'POSTGRES_INITDB_ARGS=--auth-local=trust --auth-host=scram-sha-256\n').encode())
    socket_dir = allocation / 'd4-deliver-db-socket'
    postgres_mounts = []
    if deliver:
        socket_dir.mkdir(mode=0o755)
        os.chown(socket_dir, *pg_user)
        socket_dir.chmod(0o755)
        postgres_mounts = ['--mount', f'type=bind,src={socket_dir},dst={POSTGRES_SOCKET}']
    try:
        db_id = docker(
            'run', '--detach', '--pull=never', '--name', db_name, '--network', network, '--network-alias', db_name,
            '--label', owner, '--label', f'{ROLE_LABEL}=postgres', '--memory', '512m', '--cpus', '1',
            '--pids-limit', '96', '--security-opt', 'no-new-privileges', '--ulimit', 'core=0:0',
            '--log-driver', 'none', '--env-file', str(env_path),
            '--mount', f'type=volume,src={data_volume},dst=/var/lib/postgresql/data',
            *postgres_mounts, db_image, 'postgres', '-c', 'unix_socket_permissions=0777',
            '-c', 'listen_addresses=' + ('' if deliver else '*'), stage='postgres_create',
        )
    finally:
        env_path.unlink()
    require(HEX64.fullmatch(db_id), 'unexpected_postgres_identity')
    cluster = configure_database(db_id, password, subnet)
    if deliver:
        # The stock PostgreSQL entrypoint chmods its runtime socket directory
        # to 03775. Restore the reviewed 0755 contract after startup.
        socket_info = socket_dir.lstat()
        require(stat.S_ISDIR(socket_info.st_mode) and (socket_info.st_uid, socket_info.st_gid) == pg_user,
                'unexpected_postgres_socket_directory')
        socket_dir.chmod(0o755)

    issue_dir = allocation / ('d4-' + kind)
    issue_dir.mkdir(mode=0o700)
    os.chown(issue_dir, 2002, 2002)
    database_endpoint = (f'@/{DATABASE}?host={DB_SOCKET}' if deliver else f'@{db_name}:5432/{DATABASE}')
    env_path = allocation / (kind + '-api.env')
    api_env = {
        'DATABASE_URL': f'postgresql+asyncpg://{DB_APP}:{password}{database_endpoint}',
        'SECRET_KEY': secrets.token_urlsafe(48),
        'TENANT_MODE': 'dev',
        'AGENT_TASK_RUNTIME_ENABLED': 'true',
        'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED': 'true',
        'AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE': '/run/openqms-d4-issue/policy.json',
        'AGENT_LOCAL_TRIAL_MODE': 'disabled',
        'AGENT_TASK_ATTACHMENTS_ENABLED': 'false',
        'AGENT_R5_CONTROLLED_ENABLED': 'false',
        'E2E_MODE': 'false',
        'GRAPH_REPOSITORY': 'jsonb',
        'LLM_PROVIDER': '',
        'LLM_API_KEY': '',
        'EMBEDDING_PROVIDER': '',
        'EMBEDDING_API_KEY': '',
        'EMBEDDING_BASE_URL': '',
        'PYTHONDONTWRITEBYTECODE': '1',
    }
    write(env_path, ''.join(f'{name}={value}\n' for name, value in api_env.items()).encode())
    api_mounts = ['--mount', f'type=bind,src={issue_dir},dst=/run/openqms-d4-issue']
    if deliver:
        api_mounts += ['--mount', f'type=bind,src={socket_dir},dst={DB_SOCKET},readonly']
    try:
        # Container restart loads the new policy. Upgrade is idempotent and the
        # fixed command always takes the dedicated fixture's own database URL.
        start = ('alembic upgrade platform@head && exec uvicorn app.main:app --host 127.0.0.1 '
                 f'--port {PORT} --no-access-log --log-level critical')
        api_id = docker(
            'run', '--detach', '--pull=never', '--name', api_name, '--network', 'none' if deliver else network,
            '--label', owner, '--label', f'{ROLE_LABEL}=api', '--user', '2002:2002', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=32m',
            '--memory', '768m', '--cpus', '1', '--pids-limit', '100', '--ulimit', 'core=0:0',
            '--log-driver', 'none', '--env-file', str(env_path), '--workdir', '/app', *api_mounts,
            '--entrypoint', '/bin/sh', backend, '-ec', start, stage='candidate_api_create',
        )
    finally:
        env_path.unlink()
    require(HEX64.fullmatch(api_id), 'unexpected_candidate_api_identity')
    try:
        wait_health(api_id, PORT)
    except (ValueError, RuntimeError, subprocess.SubprocessError):
        raise ValueError(kind + '_candidate_api_unready') from None
    return dict(api_container_id=api_id, db_container_id=db_id, db_image_id=db_image,
                db_system_identifier=cluster, db_host=DB_SOCKET if deliver else db_name, api_port=PORT)


def cleanup_partial(lease, allocation, runtime, staging):
    containers, networks, volumes = docker_inventory(lease, command)
    for record in containers:
        docker('container', 'rm', '--force', record['Id'], stage='partial_container_cleanup')
    for record in networks:
        docker('network', 'rm', record['Id'], stage='partial_network_cleanup')
    for record in volumes:
        docker('volume', 'rm', record['Name'], stage='partial_volume_cleanup')
    require(not any(docker_inventory(lease, command)), 'partial_resources_remain')
    for path in (runtime, staging):
        if path is not None and os.path.lexists(path):
            trusted_directory(path, private=True)
            shutil.rmtree(path)
    shutil.rmtree(allocation)

def approved_assets(config, scenarios):
    native = None
    if 'd4-deliver' in scenarios:
        native = native_sources(NATIVE_SOURCE, config['native_manifest_sha256'])
    for scenario, key in (('d4-deliver', 'delivery_image'), ('d4-revoke', 'revoke_image')):
        if scenario in scenarios:
            record = image_record(config[key])
            require(record['Config']['User'] == '2001:2001' and record['Os'] == 'linux',
                    'reviewed receiver image identity mismatch')
    image_record(config['postgres_image'])
    return native


def published_images(slot, config):
    pr = slot['pr']
    release_path = Path(f'/var/lib/openqms-previews/pr-{pr}/current-release.json')
    trusted_directory(release_path.parent)
    release = decode(read_owned(release_path, 32768))
    require(release['sha'] == slot['merge'] and release['shared_lease'] == slot['lease'],
            'published release identity changed')
    backend = release['images']['backend']
    require(image_record(backend)['Config']['Labels']['org.opencontainers.image.revision'] == slot['merge'],
            'candidate image revision changed')
    db_image = config['postgres_image']
    require(len({db_image, backend, config['delivery_image'], config['revoke_image']}) == 4,
            'D4 application, database and receiver must use distinct images')

    # The running ordinary preview DB must be the approved image. Read only
    # selected identity fields; its password and other settings stay in Docker.
    name = f'openqms-pr-{pr}-db-1'
    image, identity, project, service = docker(
        'inspect', '--format', '{{.Image}} {{.Id}} {{index .Config.Labels "com.docker.compose.project"}} '
        '{{index .Config.Labels "com.docker.compose.service"}}', name,
    ).split()
    require(image == db_image and HEX64.fullmatch(identity)
            and project == f'openqms-pr-{pr}' and service == 'db',
            'postgres image is not the trusted preview database')
    uid = int(docker('exec', identity, 'id', '-u', 'postgres'))
    gid = int(docker('exec', identity, 'id', '-g', 'postgres'))
    require(uid > 0 and gid > 0 and uid != 2002, 'unexpected postgres socket owner')
    return backend, db_image, (uid, gid)


def create_network(lease, prefix):
    network = docker('network', 'create', '--driver', 'bridge', '--internal', '--label',
                     f'{LEASE_LABEL}={lease}', prefix, stage='private bridge creation failed')
    require(HEX64.fullmatch(network), 'invalid private bridge identity')
    [bridge] = json.loads(docker('network', 'inspect', network))
    [network_addressing] = bridge['IPAM']['Config']
    subnet = ipaddress.ip_network(network_addressing['Subnet'])
    require(subnet.version == 4 and subnet.is_private and bridge['Internal'] is True,
            'invalid private bridge subnet')
    return network, str(subnet)


def stage_native_runtime(runtime, native, permit, cell):
    raw, sources = native
    runtime.mkdir(mode=0o700)
    (runtime / 'private').mkdir(mode=0o700)
    (runtime / 'state').mkdir(mode=0o700)
    (runtime / 'state' / 'journal').mkdir(mode=0o700)
    for name, data in sources.items():
        target = runtime / name
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        write(target, data, mode=0o644)
    write(runtime / MANIFEST, raw)
    write_json(runtime / 'deployment.json', {
        'schema_version': 1, 'api_container_id': cell['api_container_id'], 'permit': permit,
    })


def allocate(slot, allocation, config, scenarios, native):
    """Allocate only the planned scenarios. Caller holds the trusted queue lock."""
    backend, db_image, pg_user = published_images(slot, config)
    lease = slot['lease']
    prefix = 'openqms-d4-' + lease
    require(not any(docker_inventory(lease, command)), 'lease already has D4 resources')
    allocation.mkdir(mode=0o700)
    runtime = staging = None
    try:
        network, subnet = create_network(lease, prefix)
        cells = {
            scenario: allocate_case(lease, scenario[3:], allocation, prefix, network, subnet, db_image, backend, pg_user)
            for scenario in sorted(scenarios)
        }
        if native is not None:
            nonce = secrets.token_hex(32)
            native_path = Path('/run/openqms-d4-' + nonce)
            staging_path = runtime_staging_path(native_path)
            require(not os.path.lexists(native_path) and not os.path.lexists(staging_path),
                    'native runtime already exists')
            runtime, staging = native_path, staging_path
            cells['d4-deliver'].update(root=str(runtime), manifest_sha256=config['native_manifest_sha256'], nonce=nonce)
        if 'd4-revoke' in cells:
            cells['d4-revoke']['revoke_image_id'] = config['revoke_image']
        now = int(time.time())
        binding = dict(slot, report_id=str(uuid4()), issued_at=now, expires_at=now + 3600)
        prepared = dict(binding=binding, cases=cells)
        # Publish the cleanup record before starting native setup; a killed
        # allocator leaves either no native directory or an owned staging tree.
        temporary_record = allocation / '.prepared.json'
        write_json(temporary_record, prepared)
        os.replace(temporary_record, allocation / 'prepared.json')
        if runtime is not None:
            permit = {'image_digest': config['delivery_image'], 'worker_sha256': config['worker_sha256'],
                      'receiver_uid': 2001, 'api_uid': 2002, 'api_port': PORT}
            stage_native_runtime(staging, native, permit, cells['d4-deliver'])
            verify_bundle(staging, config['native_manifest_sha256'])
            os.replace(staging, runtime)
        permitted_cells(prepared, binding)
    except BaseException:
        cleanup_partial(lease, allocation, runtime, staging)
        raise
