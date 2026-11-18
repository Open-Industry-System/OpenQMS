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
from portal_issue import write_private
from runtime_launch import RuntimeLaunch, decode, read_owned, require, trusted_directory, verify_bundle
from witness import DOCKER, PsqlWitness, uuid_text


ISSUE = Path(__file__).with_name('issue.py')
PRIVATE = '/run/openqms-d4-issue'
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
    expected = {'root', 'manifest_sha256', 'nonce', 'api_container_id', 'db_container_id', 'db_image_id',
                'db_system_identifier', 'db_host', 'api_port', 'control_socket'}
    for scenario, cell in prepared['cases'].items():
        require(set(cell) == expected, 'invalid D4 cell preparation fields')
        api = inventory[scenario[3:] + '-api']
        db = inventory[scenario[3:] + '-postgres']
        require(api['Id'] == cell['api_container_id'] and db['Id'] == cell['db_container_id']
                and api['Image'] == release['images']['backend'] and db['Image'] == cell['db_image_id']
                and api['State']['Running'] and db['State']['Running']
                and api['Config']['User'] == '2002:2002'
                and api['HostConfig']['CapDrop'] == ['ALL']
                and not api['HostConfig'].get('CapAdd')
                and set(api['NetworkSettings']['Networks']) == {'openqms-d4-' + binding['lease']},
                'D4 candidate API or database identity mismatch')
        directory = QUEUE_ROOT / 'd4' / binding['lease'] / scenario
        mounts = api['Mounts']
        require(len(mounts) == 1 and all(
            mount['Type'] == 'bind' and mount['Source'] == str(directory)
            and mount['Destination'] == PRIVATE and mount['RW'] is True for mount in mounts
        ), 'D4 API has a mount outside its private fixture directory')
        info = directory.lstat()
        require(directory.is_dir() and not directory.is_symlink() and info.st_uid == info.st_gid == 2002
                and info.st_mode & 0o777 == 0o700, 'D4 API fixture directory ownership mismatch')
        require(re.fullmatch('[a-z][a-z0-9-]{0,62}', cell['db_host'])
                and type(cell['api_port']) is int and 1024 <= cell['api_port'] <= 65535,
                'invalid D4 infrastructure endpoint')
        runtime = RuntimeLaunch(cell['root'], cell['manifest_sha256'], cell['nonce'], cell['api_container_id'])
        require(runtime.root == Path('/run/openqms-d4-' + runtime.nonce), 'D4 runtime root identity mismatch')
        verify_bundle(runtime.root, runtime.manifest_sha256)
        runtime.deployment()
        require(runtime.journal() is None and runtime.read_state() is None, 'D4 runtime already used')
    require(len({row['nonce'] for row in prepared['cases'].values()}) == 2, 'D4 runtime shared between cases')


def read_receiver(directory):
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open('receiver.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
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
    receiver = read_receiver(directory)
    require(set(receiver) == {'origin', 'tenant_slug', 'installation_id', 'secret', 'request_key',
                              'expected_report_id'}
            and receiver['origin'] == 'http://127.0.0.1:' + str(cell['api_port'])
            and receiver['tenant_slug'] == 'd4-' + binding['lease']
            and receiver['expected_report_id'] == binding['report_id']
            and receiver['installation_id'] == task['installation_id']
            and isinstance(receiver['secret'], str)
            and re.fullmatch('[A-Za-z0-9_-]{20,256}', receiver['secret'])
            and re.fullmatch('[a-f0-9]{32}', receiver['request_key']), 'D4 worker config binding mismatch')
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
        require(all(binding[key] == slot[key] for key in ('pr', 'head', 'merge', 'plan', 'lease'))
                and binding['expires_at'] <= slot['expires_at'], 'D4 preparation does not match current test slot')
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
