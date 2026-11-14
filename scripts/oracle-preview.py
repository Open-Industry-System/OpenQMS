#!/usr/bin/env python3
"""Installed trusted host helper. Never load Compose or commands from a PR checkout.

Caller holds /run/lock/openqms-deploy.lock across capacity, startup and publication.
This helper also takes that lock when invoked independently.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROUTES = Path('/etc/openqms/preview-routes')
CADDY = 'openqms-web-1'

def pr_number(value):
    if not re.fullmatch(r'[1-9][0-9]{0,8}', value):
        raise ValueError('PR must be a canonical positive integer under 1 billion')
    return value

def capacity(pr, active):
    pr_number(pr)
    if len(set(active) - {pr}) >= 2:
        raise ValueError('preview capacity reached (two stacks maximum)')

def owned(labels, pr):
    return labels.get('openqms.preview.pr') == pr and labels.get('com.docker.compose.project') == 'openqms-pr-' + pr

def route(pr):
    pr_number(pr)
    return f'pr-{pr}.preview.openqms.smartindustry.world {{\n\treverse_proxy openqms-pr-{pr}-web:8080\n}}\n'

def atomic(path, content):
    fd, name = tempfile.mkstemp(prefix='.route-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def publish(path, content, validate, reload):
    if path.is_symlink():
        raise ValueError('route cannot be symlink')
    previous = path.read_text() if path.exists() else None
    if content is None:
        path.unlink(missing_ok=True)
    else:
        atomic(path, content)
    try:
        validate()
        reload()
    except Exception:
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            atomic(path, previous)
        reload()
        raise

def run(*args):
    return subprocess.check_output(args, text=True).strip()

def resources(kind, pr=None):
    cmd = ['docker', kind, 'ls', '-q', '--filter', 'label=openqms.preview.pr' + ('=' + pr if pr else '')]
    if kind == 'container': cmd.insert(3, '-a')
    ids = run(*cmd).splitlines()
    if not ids: return []
    return json.loads(run('docker', kind, 'inspect', *ids))

def labels(item, kind):
    return (item.get('Config', {}).get('Labels') if kind == 'container' else item.get('Labels')) or {}

def active_prs():
    result = set()
    for kind in ['container', 'volume', 'network']:
        for item in resources(kind):
            value = labels(item, kind).get('openqms.preview.pr')
            pr_number(value)
            if not owned(labels(item, kind), value):
                raise ValueError('preview inventory contains ambiguous ownership')
            result.add(value)
    return result

def cleanup(pr):
    # Inventory and verify every resource before changing anything. Route first.
    inventory = {kind: resources(kind, pr) for kind in ['container', 'volume', 'network']}
    for kind, items in inventory.items():
        if any(not owned(labels(item, kind), pr) for item in items):
            raise ValueError('refusing cleanup: resource ownership mismatch')
    publish(ROUTES / f'pr-{pr}.caddy', None, validate, reload)
    for kind, items in inventory.items():
        for item in items:
            identity = item.get('Id') if kind != 'volume' else item.get('Name')
            if kind == 'container':
                run('docker', 'container', 'stop', identity)
            run('docker', kind, 'rm', identity)
    # Revoke this stack's secrets and free its fixed loopback slot only after
    # every owned container/volume/network has been removed successfully.
    secret = Path('/var/lib/openqms-previews') / ('pr-' + pr) / 'preview.env'
    if secret.is_symlink():
        raise ValueError('refusing symlink secret cleanup')
    secret.unlink(missing_ok=True)

def validate():
    run('docker', 'exec', CADDY, 'caddy', 'validate', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile')

def reload():
    run('docker', 'exec', CADDY, 'caddy', 'reload', '--address', 'unix//tmp/openqms-caddy-admin.sock', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['capacity', 'publish', 'cleanup'])
    parser.add_argument('pr', type=pr_number)
    args = parser.parse_args()
    with open('/run/lock/openqms-deploy.lock', 'a') as lock:
        # Inherited flock descriptor must be passed by the trusted orchestrator,
        # otherwise take our own lock. Never trust environment claims of locking.
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'cleanup': cleanup(args.pr)
        else:
            capacity(args.pr, active_prs())
            if args.action == 'publish':
                publish(ROUTES / f'pr-{args.pr}.caddy', route(args.pr), validate, reload)

if __name__ == '__main__': main()
