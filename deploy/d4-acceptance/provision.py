#!/usr/bin/env python3
"""Prepare and witness two synthetic D4 tasks in pre-approved lease containers."""
import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import time

from browser import SCENARIOS, validate_binding
from cleanup import database_binding, docker_inventory, command
from executor import QUEUE_ROOT, hold_test_slot
from issue import DB_SOCKET
from portal_issue import write_private
from runtime_launch import IMAGE, RuntimeLaunch, decode, read_owned, require, trusted_directory, verify_bundle
from witness import DOCKER, PsqlWitness, uuid_text


ISSUE = Path(__file__).with_name('issue.py')
PRIVATE = '/run/openqms-d4-issue'
POSTGRES_SOCKET = '/var/run/postgresql'
PYTHON = ('/usr/local/bin/python', '-I', '-B')


def application(api, arguments, *, data=None, timeout=60):
    result = subprocess.run(
        (*DOCKER, 'container', 'exec', '--interactive', '--user', '2002:2002', '--workdir', '/app',
         api, *PYTHON, *arguments),
        input=data, env={}, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False,
    )
    require(result.returncode == 0 and len(result.stdout) <= 8192, 'D4 application operation failed')
    return result.stdout


def wait_health(api, port):
    source = (
        'import http.client,sys\n'
        'connection = http.client.HTTPConnection("127.0.0.1", int(sys.argv[1]), timeout=1)\n'
        'connection.request("GET", "/api/health")\n'
        'if connection.getresponse().status != 200: raise SystemExit(1)\n'
        'connection.close()\n'
    )
    until = time.monotonic() + 25
    while time.monotonic() < until:
        try:
            application(api, ('-c', source, str(port)), timeout=3)
            return
        except (RuntimeError, subprocess.TimeoutExpired):
            time.sleep(0.5)
    raise ValueError('D4 candidate API did not become ready')


def matches_bind_mount(mount, source, destination, *, writable):
    return (mount['Type'] == 'bind' and mount['Source'] == str(source)
            and mount['Destination'] == destination and mount['RW'] is writable)


def verified_socket_mount(api_mount, database, directory):
    if not (matches_bind_mount(api_mount, directory, DB_SOCKET, writable=False)
            and any(matches_bind_mount(mount, directory, POSTGRES_SOCKET, writable=True)
                    for mount in database['Mounts'])):
        return False
    directory_info = directory.lstat()
    if (not stat.S_ISDIR(directory_info.st_mode) or directory_info.st_mode & 0o022
            or directory_info.st_uid == 0):
        return False
    socket_info = (directory / '.s.PGSQL.5432').lstat()
    return stat.S_ISSOCK(socket_info.st_mode) and socket_info.st_uid == directory_info.st_uid


def permitted_cells(prepared, binding):
    containers, _, _ = docker_inventory(binding['lease'], command)
    inventory = {'-'.join(entry['Name'].rsplit('-', 2)[-2:]): entry
                 for entry in containers}
    release_file = Path(f'/var/lib/openqms-previews/pr-{binding["pr"]}/current-release.json')
    trusted_directory(release_file.parent)
    release = decode(read_owned(release_file, 32768))
    require(release['sha'] == binding['merge'] and release['shared_lease'] == binding['lease'],
            'D4 infrastructure does not match the deployed release')
    require(set(prepared) == {'binding', 'cases'} and set(prepared['cases']) == set(SCENARIOS)
            and len(inventory) == 4, 'two exact D4 infrastructure cells required')
    common = {'api_container_id', 'db_container_id', 'db_image_id',
              'db_system_identifier', 'db_host', 'api_port'}
    for scenario, cell in prepared['cases'].items():
        runtime_fields = {'root', 'manifest_sha256', 'nonce'} if scenario == 'd4-deliver' else {'revoke_image_id'}
        require(set(cell) == common | runtime_fields, 'invalid D4 cell preparation fields')
        api = inventory[scenario[3:] + '-api']
        db = inventory[scenario[3:] + '-postgres']
        require(api['Id'] == cell['api_container_id'] and db['Id'] == cell['db_container_id']
                and api['Image'] == release['images']['backend'] and db['Image'] == cell['db_image_id']
                and api['State']['Running'] and db['State']['Running']
                and api['Config']['User'] == '2002:2002'
                and api['HostConfig']['CapDrop'] == ['ALL']
                and not api['HostConfig'].get('CapAdd'),
                'D4 candidate API or database identity mismatch')
        directory = QUEUE_ROOT / 'd4' / binding['lease'] / scenario
        mounts = api['Mounts']
        fixture = [mount for mount in mounts if matches_bind_mount(mount, directory, PRIVATE, writable=True)]
        require(len(fixture) == 1, 'D4 API has an invalid private fixture mount')
        if scenario == 'd4-deliver':
            # A Docker bridge starts embedded DNS in this namespace. The native
            # receiver requires only its candidate's loopback listener.
            require(api['HostConfig']['NetworkMode'] == 'none'
                    and set(api['NetworkSettings']['Networks']) == {'none'}
                    and cell['db_host'] == DB_SOCKET,
                    'D4 native delivery requires an isolated API namespace')
            require(len(mounts) == 2 and any(
                verified_socket_mount(mount, db, directory.with_name('d4-deliver-db-socket'))
                for mount in mounts if mount is not fixture[0]
            ), 'D4 native delivery requires its own read-only database socket')
        else:
            require(set(api['NetworkSettings']['Networks']) == {'openqms-d4-' + binding['lease']}
                    and len(mounts) == 1 and re.fullmatch('[a-z][a-z0-9-]{0,62}', cell['db_host']),
                    'D4 revocation requires the isolated lease bridge and fixture mount')
        info = directory.lstat()
        require(directory.is_dir() and not directory.is_symlink() and info.st_uid == info.st_gid == 2002
                and info.st_mode & 0o777 == 0o700, 'D4 API fixture directory ownership mismatch')
        require(type(cell['api_port']) is int and 1024 <= cell['api_port'] <= 65535,
                'invalid D4 infrastructure API endpoint')
        if scenario == 'd4-deliver':
            runtime = RuntimeLaunch(cell['root'], cell['manifest_sha256'], cell['nonce'], cell['api_container_id'])
            require(runtime.root == Path('/run/openqms-d4-' + runtime.nonce), 'D4 runtime root identity mismatch')
            verify_bundle(runtime.root, runtime.manifest_sha256)
            runtime.deployment()
            require(runtime.journal() is None and runtime.read_state() is None, 'D4 runtime already used')
        else:
            image = cell['revoke_image_id']
            require(IMAGE.fullmatch(image) and image != api['Image'] and image != db['Image'],
                    'dedicated, separately reviewed revocation image required')
            require(command(*DOCKER, 'image', 'inspect', '--format', '{{.Id}}', image) == image,
                    'reviewed revocation receiver image unavailable')


def read_case_file(directory, filename):
    require(filename in {'receiver.json', 'private-state.json'}, 'unsupported D4 private record')
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        with os.fdopen(descriptor, 'rb') as file:
            info = os.fstat(file.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 2002
                    and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
                    'D4 candidate receiver file ownership mismatch')
            raw = file.read(8193)
    finally:
        os.close(directory_fd)
    require(len(raw) <= 8192, 'D4 receiver config is oversized')
    return decode(raw)


def seed(cell, binding, source, directory):
    api = cell['api_container_id']
    payload = json.dumps({key: cell[key] for key in ('db_host', 'db_system_identifier', 'api_port')}
                         | {'binding': binding}).encode()
    wait_health(api, cell['api_port'])
    initial = decode(application(api, ('-c', source, 'prepare'), data=payload))
    command(*DOCKER, 'container', 'restart', '--time', '5', api)
    wait_health(api, cell['api_port'])
    task = decode(application(api, ('-c', source, 'task'), data=payload))
    fields = {'tenant_id', 'schema', 'generation', 'report_id', 'installation_id', 'executor_user_id'}
    require(set(initial) == fields and set(task) == fields | {'task_id', 'grant_id'}
            and all(task[key] == initial[key] for key in fields)
            and task['report_id'] == binding['report_id'], 'D4 task does not match its seeded allocation')
    for key in ('report_id', 'tenant_id', 'installation_id', 'executor_user_id', 'task_id', 'grant_id'):
        uuid_text(task[key])
    witness = PsqlWitness(cell['db_container_id'], cell['db_image_id'], cell['db_system_identifier'],
                          binding['lease'], task['tenant_id'], task['schema'], task['generation'])
    snapshot = witness.snapshot(task['report_id'], task['task_id'], task['installation_id'], task['grant_id'])
    require(snapshot.task_status == 'ready' and snapshot.run_status == 'pending'
            and snapshot.lease_epoch == 0 and snapshot.grant_live, 'D4 ready task was not independently witnessed')

    # The per-case bind mount is already identity-checked. Open the one fixed
    # credential file directly and keep it out of Docker and process output.
    receiver = read_case_file(directory, 'receiver.json')
    require(set(receiver) == {'origin', 'tenant_slug', 'installation_id', 'secret', 'request_key',
                              'expected_report_id'}
            and receiver['origin'] == 'http://127.0.0.1:' + str(cell['api_port'])
            and receiver['tenant_slug'] == 'd4-' + binding['lease']
            and receiver['expected_report_id'] == binding['report_id']
            and receiver['installation_id'] == task['installation_id']
            and isinstance(receiver['secret'], str)
            and re.fullmatch('[A-Za-z0-9_-]{20,256}', receiver['secret'])
            and re.fullmatch('[a-f0-9]{32}', receiver['request_key']), 'D4 worker config binding mismatch')
    if 'root' in cell:
        private = Path(cell['root']) / 'private'
        trusted_directory(private, private=True)
        write_private(private / 'config.json', receiver)

    return ({key: item for key, item in cell.items() if key not in {'api_port', 'db_host'}}
            | {key: task[key] for key in ('tenant_id', 'schema', 'generation', 'task_id', 'grant_id', 'installation_id')})


def provision(lease):
    require(re.fullmatch('[a-f0-9]{32}', lease), 'invalid D4 lease')
    with hold_test_slot():
        slot = database_binding(lease, 'testing')
        directory = QUEUE_ROOT / 'd4' / lease
        trusted_directory(directory, private=True)
        prepared = decode(read_owned(directory / 'prepared.json', 32768, private=True))
        binding = prepared['binding']
        validate_binding(binding)
        require(all(binding[key] == slot[key] for key in ('pr', 'head', 'merge', 'plan', 'lease')),
                'D4 preparation does not match current test slot')
        require(not (directory / 'profile.json').exists() and not (directory / 'profile.json').is_symlink(),
                'D4 profile already exists')
        permitted_cells(prepared, binding)
        source = 'import sys; sys.path.insert(0, "/app")\n' + read_owned(ISSUE, 65536).decode()
        cases = {name: seed(cell, binding, source, directory / name)
                 for name, cell in prepared['cases'].items()}
        validate_binding(binding)
        portal = pwd.getpwnam('openqms-d4-portal')
        group = grp.getgrnam('openqms-d4-portal')
        require(portal.pw_uid > 0 and portal.pw_gid == group.gr_gid > 0, 'D4 portal account invalid')
        write_private(directory / 'profile.json', dict(binding=binding, portal_uid=portal.pw_uid,
                                                       portal_gid=group.gr_gid, cases=cases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lease', required=True)
    args = parser.parse_args()
    try:
        provision(args.lease)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        raise SystemExit('D4 fixture issuance failed; current lease must be cleaned') from None


if __name__ == '__main__':
    main()
