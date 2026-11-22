#!/usr/bin/env python3
"""Reclaim one retired D4 test lease and verify that its resources are gone."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time

from executor import QUEUE_ROOT, root_private, socket_path_for
from runtime_launch import (
    HEX64, NONCE_LABEL, SYSTEMCTL, RuntimeLaunch, decode, read_owned, require,
    trusted_directory, verify_bundle,
)
from witness import DOCKER, LEASE_LABEL, ROLE_LABEL


RUN_ROOT = Path('/run/openqms-d4-acceptance/leases')


def command(*args):
    result = subprocess.run(args, env={}, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=15, check=False)
    require(result.returncode == 0 and len(result.stdout) <= 262144, 'D4 cleanup command failed')
    return result.stdout.decode().strip()


def database_binding(lease, phase):
    root_private(QUEUE_ROOT, directory=True)
    path = QUEUE_ROOT / 'queue.sqlite3'
    root_private(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
        slot = connection.execute(
            'SELECT lease, release, phase FROM slot WHERE singleton = 1'
        ).fetchone()
    require(slot and slot[0] == lease and slot[2] == phase, 'D4 lease phase does not authorize this action')
    return dict(json.loads(slot[1]), lease=lease)


def stop_unit(unit, run=command):
    load = run(SYSTEMCTL, 'show', '--property=LoadState', '--value', unit)
    if load != 'not-found':
        require(load == 'loaded', 'D4 cleanup unit state unknown')
        run(SYSTEMCTL, 'stop', unit)
    require(run(SYSTEMCTL, 'show', '--property=ActiveState', '--value', unit) == 'inactive',
            'D4 cleanup unit remains active')


def objects(kind, label, run):
    # These three Docker list commands support labels and immutable full IDs.
    ids = run(*DOCKER, kind, 'ls', '--quiet', *(['--all', '--no-trunc'] if kind == 'container'
                                               else ['--no-trunc'] if kind == 'network' else []),
              '--filter', f'label={label}').splitlines()
    require(len(ids) == len(set(ids)), 'duplicate D4 Docker inventory')
    if not ids:
        return []
    rows = json.loads(run(*DOCKER, kind, 'inspect', *ids))
    require(isinstance(rows, list) and len(rows) == len(ids), 'unknown D4 Docker inventory')
    field = 'Name' if kind == 'volume' else 'Id'
    require({row[field] for row in rows} == set(ids), 'D4 Docker inventory changed')
    return rows


def docker_inventory(lease, run):
    prefix = 'openqms-d4-' + lease
    owner = f'{LEASE_LABEL}={lease}'
    containers = objects('container', owner, run)
    networks = objects('network', owner, run)
    volumes = objects('volume', owner, run)
    names = {f'/{prefix}-{case}-{role}': role for case in ('deliver', 'revoke') for role in ('api', 'postgres')}
    volume_names = {f'{prefix}-{case}-postgres-data' for case in ('deliver', 'revoke')}
    receiver_name = f'/{prefix}-revoke-receiver'
    names[receiver_name] = 'receiver'
    revoke_api = next((row['Id'] for row in containers if row['Name'] == f'/{prefix}-revoke-api'), None)
    require(len(containers) <= 5 and len(networks) <= 1 and len(volumes) <= 2,
            'unexpected D4 Docker inventory')
    for row in containers:
        labels = row['Config']['Labels']
        network_names = set(row['NetworkSettings']['Networks'])
        allowed_networks = {prefix}
        if row['Name'] == f'/{prefix}-deliver-api' and row['HostConfig'].get('NetworkMode') == 'none':
            allowed_networks = {'none'}
        require(row['Name'] in names and labels.get(LEASE_LABEL) == lease
                and labels.get(ROLE_LABEL) == names[row['Name']] and HEX64.fullmatch(row['Id'])
                and network_names <= allowed_networks
                and not row['HostConfig'].get('PortBindings')
                and not row['HostConfig'].get('Privileged'),
                'D4 cleanup container ownership mismatch')
        if row['Name'] == receiver_name:
            require(revoke_api and row['HostConfig'].get('NetworkMode') == 'container:' + revoke_api
                    and row['Config'].get('User') == '2001:2001',
                    'D4 revoke receiver namespace mismatch')
    for network in networks:
        endpoints = network.get('Containers') or {}
        require(network['Name'] == prefix and HEX64.fullmatch(network['Id'])
                and network.get('Labels', {}).get(LEASE_LABEL) == lease
                and network.get('Internal') is True and network.get('Driver') == 'bridge'
                and set(endpoints) <= {row['Id'] for row in containers},
                'D4 cleanup network ownership mismatch')
    for volume in volumes:
        require(volume['Name'] in volume_names and volume.get('Labels', {}).get(LEASE_LABEL) == lease
                and volume['Driver'] == 'local' and not volume.get('Options'),
                'D4 cleanup volume ownership mismatch')
    return containers, networks, volumes


def native_runtimes(allocation, binding):
    for name in ('profile.json', 'prepared.json'):
        try:
            profile = decode(read_owned(allocation / name, 32768, private=True))
            break
        except FileNotFoundError:
            continue
    else:
        # A preparation record is required before assembling native roots.
        return ()
    require(all(profile['binding'][key] == binding[key] for key in ('pr', 'head', 'merge', 'plan', 'lease')),
            'D4 cleanup launch profile belongs to another release')
    require(set(profile['cases']) == {'d4-deliver', 'd4-revoke'}, 'D4 cleanup cases missing')
    case = profile['cases']['d4-deliver']
    runtime = RuntimeLaunch(case['root'], case['manifest_sha256'], case['nonce'], case['api_container_id'])
    require(runtime.root == Path('/run/openqms-d4-' + runtime.nonce), 'D4 cleanup native root mismatch')
    return (runtime,)


def reclaim_runtime(runtime, run):
    owner = f'{NONCE_LABEL}={runtime.nonce}'
    if not runtime.root.exists() and not runtime.root.is_symlink():
        require(not objects('container', owner, run), 'D4 receiver remains without its runtime root')
        return
    verify_bundle(runtime.root, runtime.manifest_sha256)
    stop_unit(f'openqms-d4-controller-{runtime.nonce}.service', run)
    stop_unit(f'openqms-d4-watchdog-{runtime.nonce}.service', run)
    journal = runtime.journal()
    if journal is not None:
        if journal['state'] != 'closed':
            runtime.maintain()
        journal = runtime.wait_reclaimed(time.monotonic() + 4)
        runtime.remove_receiver(journal, runtime.deployment())
    require(not objects('container', owner, run), 'D4 receiver remains after reclaim')
    shutil.rmtree(runtime.root)


def cleanup(lease, *, run=command):
    require(isinstance(lease, str) and re.fullmatch('[a-f0-9]{32}', lease), 'invalid D4 cleanup lease')
    binding = database_binding(lease, 'releasing')
    allocation = QUEUE_ROOT / 'd4' / lease
    if not allocation.exists() and not allocation.is_symlink():
        return
    trusted_directory(allocation, private=True)
    portal = RUN_ROOT / lease
    has_portal = portal.exists() or portal.is_symlink()
    if has_portal:
        trusted_directory(portal, private=True)
    runtimes = native_runtimes(allocation, binding)
    # Validate the complete application inventory before making any change.
    docker_inventory(lease, run)
    for service in ('portal', 'executor'):
        stop_unit(f'openqms-d4-acceptance-{service}@{lease}.service', run)
    endpoint = socket_path_for(lease)
    if endpoint.exists() or endpoint.is_symlink():
        trusted_directory(endpoint.parent)
        info = endpoint.lstat()
        require(stat.S_ISSOCK(info.st_mode) and info.st_uid == 0, 'D4 cleanup socket ownership mismatch')
        endpoint.unlink()
    for runtime in runtimes:
        reclaim_runtime(runtime, run)
    containers, networks, volumes = docker_inventory(lease, run)
    for row in sorted(containers, key=lambda row: row['Config']['Labels'][ROLE_LABEL] != 'receiver'):
        run(*DOCKER, 'container', 'rm', '--force', row['Id'])
    for row in networks:
        run(*DOCKER, 'network', 'rm', row['Id'])
    for row in volumes:
        run(*DOCKER, 'volume', 'rm', row['Name'])
    require(not any(docker_inventory(lease, run)), 'D4 Docker resources remain after cleanup')
    if has_portal:
        shutil.rmtree(portal)
    shutil.rmtree(allocation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lease', required=True)
    args = parser.parse_args()
    if sys.platform != 'linux' or not shutil.rmtree.avoids_symlink_attacks:
        raise SystemExit('trusted Linux D4 cleanup required')
    try:
        cleanup(args.lease)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        raise SystemExit('D4 cleanup could not verify resource ownership or removal') from None


if __name__ == '__main__':
    main()
