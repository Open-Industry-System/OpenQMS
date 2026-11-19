"""Run the reviewed revocation receiver and witness the same run across its barrier."""
from contextlib import suppress
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time

from cleanup import docker_inventory
from executor import QUEUE_ROOT
from provision import read_case_file
from runtime_launch import HEX64, IMAGE, decode, require
from witness import DOCKER, LEASE_LABEL, ROLE_LABEL, verify_revocation


BUDGET = 32
MAX_LINE = 2048


def plan(case, binding, baseline):
    directory = QUEUE_ROOT / 'd4' / binding['lease'] / 'd4-revoke'
    receiver = read_case_file(directory, 'receiver.json')
    state = read_case_file(directory, 'private-state.json')
    config = state['config']
    require(config['binding'] == binding and state['report_id'] == binding['report_id']
            and state['installation_id'] == case['installation_id']
            and state['tenant_id'] == case['tenant_id'] and state['schema'] == case['schema']
            and state['generation'] == case['generation']
            and receiver['installation_id'] == case['installation_id']
            and receiver['expected_report_id'] == binding['report_id']
            and receiver['tenant_slug'] == state['slug'] == 'd4-' + binding['lease']
            and receiver['origin'] == 'http://127.0.0.1:' + str(config['api_port'])
            and type(config['api_port']) is int and 1024 <= config['api_port'] <= 65535
            and state['admin_username'] == 'd4-admin@example.test'
            and re.fullmatch('[A-Za-z0-9_-]{48}', state['admin_password']),
            'D4 revoke configuration does not match the dedicated case')
    return dict(receiver=receiver, admin_username=state['admin_username'], admin_password=state['admin_password'],
                task_id=baseline.task_id, run_id=baseline.run_id, grant_id=baseline.grant_id)


def docker(*args, timeout=5):
    result = subprocess.run((*DOCKER, *args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=timeout, check=False, env={})
    require(result.returncode == 0 and len(result.stdout) <= 262144, 'D4 revoke runtime command failed')
    return result.stdout.decode().strip()


def read_line(stream, deadline):
    result = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(stream, selectors.EVENT_READ)
        while len(result) <= MAX_LINE:
            remaining = deadline - time.monotonic()
            require(remaining > 0 and selector.select(remaining), 'D4 receiver output deadline expired')
            chunk = os.read(stream.fileno(), 1)
            require(chunk, 'D4 receiver closed before providing a receipt')
            if chunk == b'\n':
                return decode(result)
            result.extend(chunk)
    raise ValueError('D4 receiver receipt exceeds the bound')


def create(case, lease):
    image = case['revoke_image_id']
    api = case['api_container_id']
    require(IMAGE.fullmatch(image) and HEX64.fullmatch(api), 'D4 receiver and API must be pinned by ID')
    containers, _, _ = docker_inventory(lease, lambda *args: docker(*args[len(DOCKER):]))
    prefix = 'openqms-d4-' + lease
    require(any(row['Id'] == api and row['Name'] == f'/{prefix}-revoke-api' and row['State']['Running']
                for row in containers), 'D4 revoke API namespace does not match the active lease')
    receiver = docker(
        'container', 'create', '--pull=never', '--interactive', '--name', prefix + '-revoke-receiver',
        '--label', f'{LEASE_LABEL}={lease}', '--label', f'{ROLE_LABEL}=receiver',
        '--network', 'container:' + api, '--user', '2001:2001',
        '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--memory', '64m', '--pids-limit', '16', '--cpus', '0.5', '--ulimit', 'core=0:0',
        '--log-driver', 'none', image,
    )
    require(HEX64.fullmatch(receiver), 'unknown D4 revoke receiver identity')
    return receiver


def exchange(process, payload, baseline, snapshot, deadline):
    encoded = json.dumps(payload, separators=(',', ':')).encode('ascii') + b'\n'
    require(len(encoded) <= MAX_LINE, 'D4 receiver input exceeds the bound')
    process.stdin.write(encoded)
    process.stdin.flush()
    initial = read_line(process.stdout, deadline)
    expected = {name: getattr(baseline, name) for name in (
        'task_id', 'run_id', 'report_id', 'installation_id', 'grant_id',
    )}
    require(initial == dict(expected, stage='authorized'), 'D4 authorized receipt identity changed')
    before = snapshot(deadline)
    require(before.run_id == baseline.run_id and before.run_status == 'active'
            and before.lease_epoch == 1 and before.run_live and before.grant_live
            and before.receipts == before.committed_audits == baseline.receipts + 1
            and before.finish_audits == 0 and before.revoke_audits == baseline.revoke_audits,
            'D4 authorized read was not witnessed before revocation')
    require(time.monotonic() < deadline, 'D4 revoke request expired')
    process.stdin.write(b'revoke\n')
    process.stdin.flush()
    process.stdin.close()

    receipt = read_line(process.stdout, deadline)
    after = snapshot(deadline)
    verify_revocation(before, after, receipt)
    remaining = deadline - time.monotonic()
    require(remaining > 0 and process.wait(timeout=remaining) == 0, 'D4 revoke receiver did not complete')
    return before, after


def run_revocation(case, binding, baseline, snapshot):
    payload = plan(case, binding, baseline)
    receiver = create(case, binding['lease'])
    try:
        with subprocess.Popen(
            (*DOCKER, 'container', 'start', '--attach', '--interactive', receiver),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={},
        ) as process:
            try:
                return exchange(process, payload, baseline, snapshot, time.monotonic() + BUDGET)
            finally:
                if process.poll() is None:
                    with suppress(ProcessLookupError):
                        process.kill()
    finally:
        # A receipt cannot leave the host until the pinned one-shot receiver is gone.
        docker('container', 'rm', '--force', receiver)
        remaining = docker('container', 'ls', '--all', '--quiet', '--no-trunc', '--filter', 'id=' + receiver)
        require(not remaining, 'D4 revoke receiver reclamation could not be confirmed')
