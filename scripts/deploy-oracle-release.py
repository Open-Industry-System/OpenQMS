#!/usr/bin/env python3
"""Trusted hosted-runner production deployment. Never log runtime secrets or execute PR deployment scripts."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import quote

TRUSTED = Path(__file__).resolve().parents[1]
CONTROLLER_FILES = ('scripts/oracle-production-remote.py', 'scripts/check-release-tree.py', 'docker-compose.prod.yml', 'deploy/preview-edge.override.yml', 'deploy/production-edge-Caddyfile', 'compose.preview.yml', 'scripts/oracle-preview-remote.py', 'scripts/oracle-preview.py', 'scripts/oracle-preview-initialize.py', 'deploy/preview-Caddyfile')


def run(argv, *, env=None, cwd=None, data=None):
    result = subprocess.run(argv, input=data, capture_output=True, env=env, cwd=cwd)
    if result.returncode:
        # Subprocess output can contain DSNs/production dotenv values. Never relay it.
        raise RuntimeError('deployment subprocess failed: ' + Path(argv[0]).name)
    return result.stdout


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(source):
    required = ('RELEASE_SHA', 'ORACLE_SSH_TARGET', 'ORACLE_SSH_KEY', 'ORACLE_KNOWN_HOSTS', 'ORACLE_REVALIDATE_CMD')
    if any(not source.get(key) for key in required):
        raise ValueError('missing production deployment configuration')
    if source.get('RELEASE_KIND') not in {'production', 'preview'} or not re.fullmatch(r'[0-9a-f]{40}', source['RELEASE_SHA']):
        raise ValueError('production release identity required')
    target = source['ORACLE_SSH_TARGET']
    if not re.fullmatch(r'openqms-deploy@[A-Za-z0-9.-]+', target):
        raise ValueError('dedicated openqms-deploy SSH account required')
    for key in ('ORACLE_SSH_KEY', 'ORACLE_KNOWN_HOSTS'):
        path = Path(source[key])
        if not path.is_absolute() or path.is_symlink() or not path.is_file() or not path.stat().st_size:
            raise ValueError('pinned SSH file unavailable')
        if key == 'ORACLE_SSH_KEY' and path.stat().st_mode & 0o077:
            raise ValueError('SSH key must have owner-only permissions')
    if source.get('DATABASE_URL') or source.get('TEST_DATABASE_URL') or source.get('OPENQMS_TEST_RESOURCE_FILE'):
        raise ValueError('ambient database configuration is forbidden')
    result = {key: source[key] for key in required} | {'RELEASE_KIND': source['RELEASE_KIND']}
    if result['RELEASE_KIND'] == 'preview':
        if not re.fullmatch(r'[1-9][0-9]{0,8}', source.get('PREVIEW_PR', '')):
            raise ValueError('preview PR required')
        result['PREVIEW_PR'] = source['PREVIEW_PR']
    return result


def revalidate(context):
    run(['/bin/bash', '-euo', 'pipefail', '-c', context['ORACLE_REVALIDATE_CMD']])


def ssh_args(context):
    return ['ssh', '-i', context['ORACLE_SSH_KEY'], '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + context['ORACLE_KNOWN_HOSTS'], '-o', 'ConnectionAttempts=1', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3']


def remote(context, action, *, data=None):
    command = [context['RELEASE_KIND'], action]
    if context['RELEASE_KIND'] == 'preview':
        command.append(context['PREVIEW_PR'])
    command += [context['RELEASE_SHA'], context['manifest_hash'], context['controller_hash']]
    if action in {'identity', 'migrate', 'initialize', 'preflight', 'rollout'}:
        command.append(json.dumps(context['images'], separators=(',', ':')))
    return run(ssh_args(context) + [context['ORACLE_SSH_TARGET'], shlex.join(command)], data=data)



def acquire_lease(context):
    command = [context['RELEASE_KIND'], 'lock']
    if context['RELEASE_KIND'] == 'preview':
        command.append(context['PREVIEW_PR'])
    command += [context['RELEASE_SHA'], context['manifest_hash'], context['controller_hash']]
    process = subprocess.Popen(ssh_args(context) + [context['ORACLE_SSH_TARGET'], shlex.join(command)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if not select.select([process.stdout], [], [], 30)[0] or process.stdout.readline() != b'locked\n':
        process.terminate()
        process.wait(timeout=10)
        raise ValueError('exclusive host deployment lease unavailable')
    return process


def test_environment(context):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('PG', 'LLM_', 'EMBEDDING_', 'ORACLE_', 'OPENQMS_')) or key in {'GH_TOKEN', 'GITHUB_TOKEN'} or key in {'DATABASE_URL', 'TEST_DATABASE_URL', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB', 'OPENQMS_TEST_RESOURCE_FILE', 'OPENQMS_SDK_WHEEL'}:
            env.pop(key, None)
    env.update(TEST_DATABASE_URL=context['test_url'], DATABASE_URL=context['test_url'], OPENQMS_TEST_RESOURCE_FILE=context['resource'], SECRET_KEY='release-check-only-not-production-secret', SDK_PYTHON_BIN=context['python'], PYTHON_BIN=context['python'])
    return env


def tracked_unchanged(context):
    # Candidate archive remains data: every deployable tracked byte/mode stays pinned.
    source = Path(context['source_root'])
    for line in Path(context['manifest']).read_text().splitlines():
        mode, digest, path = line.split(' ', 2)
        path = path.lstrip(' ')
        candidate = source / path
        if candidate.is_symlink() or not candidate.is_file() or sha256(candidate) != digest or (candidate.stat().st_mode & 0o777) != (0o755 if mode == '100755' else 0o644):
            raise ValueError('checked source changed during validation')


def phase(context, name):
    if name == 'identity':
        remote(context, 'verify')
        payload = json.loads(remote(context, 'identity'))
        sys.path.insert(0, str(TRUSTED / 'scripts'))
        from database_identity import DatabaseIdentity, resolve_live_identity
        if resolve_live_identity(context['target_url']) != DatabaseIdentity.from_json(json.dumps(payload)):
            raise ValueError('tunnel target does not match production runtime')
    elif name == 'migrate':
        phase(context, 'identity')
        remote(context, 'migrate')
    elif name == 'check':
        # Attest the exact successful unprivileged CI run. Candidate scripts must
        # never execute on a runner holding deployment credentials.
        revalidate(context)
        tracked_unchanged(context)
    elif name == 'initialize':
        if context['RELEASE_KIND'] != 'preview':
            raise ValueError('production initialization forbidden')
        phase(context, 'identity')
        remote(context, 'initialize')
    elif name == 'preflight':
        phase(context, 'identity')
        remote(context, 'preflight')
    elif name == 'rollout':
        revalidate(context)
        tracked_unchanged(context)
        phase(context, 'identity')
        remote(context, 'rollout')
    else:
        raise ValueError('invalid deployment phase')


def save(path, context):
    path.write_text(json.dumps(context))
    path.chmod(0o600)


def create_test_database(context, private):
    nonce = secrets.token_hex(16)
    name = 'openqms-release-' + nonce
    password = secrets.token_hex(24)
    # Credentials travel only through the child environment; not process arguments/output.
    env = dict(os.environ, POSTGRES_PASSWORD=password)
    run(['docker', 'run', '-d', '--name', name, '--label', 'openqms.owner=' + nonce, '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_USER=qms_release', '-e', 'POSTGRES_DB=postgres', '-p', '127.0.0.1::5432', 'pgvector/pgvector:pg15'], env=env)
    context['test_container'] = name
    context['test_owner'] = nonce
    info = json.loads(run(['docker', 'inspect', name]))[0]
    if info['Config']['Image'] != 'pgvector/pgvector:pg15' or info['Config'].get('Labels', {}).get('openqms.owner') != nonce or not re.fullmatch(r'[0-9a-f]{64}', info['Id']):
        raise ValueError('test container ownership failed')
    mapping = info['NetworkSettings']['Ports']['5432/tcp']
    if len(mapping) != 1 or mapping[0]['HostIp'] != '127.0.0.1' or not re.fullmatch(r'[1-9][0-9]{0,4}', mapping[0]['HostPort']):
        raise ValueError('test database must bind only loopback')
    port = int(mapping[0]['HostPort'])
    context['test_container_id'] = info['Id']
    context['test_owner'] = nonce
    registration = private / 'test-resource.json'
    save(registration, dict(container=name, container_id=info['Id'], owner_nonce=nonce, image='pgvector/pgvector:pg15', host='127.0.0.1', port=port, test_database='qms_test', application_database='postgres'))
    context['resource'] = str(registration)
    context['test_url'] = f'postgresql+asyncpg://qms_release:{password}@127.0.0.1:{port}/qms_test'
    for _ in range(60):
        ready = subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'qms_release', '-d', 'postgres'], capture_output=True)
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise ValueError('test database did not become ready')
    run(['make', '--silent', '-C', context['test_root'], 'check-test-db', 'PYTHON_BIN=' + context['python']], env=test_environment(context))


def cleanup_test(context):
    if 'test_container_id' not in context:
        return
    info = json.loads(run(['docker', 'inspect', context['test_container']]))[0]
    if info['Id'] != context['test_container_id'] or info['Config'].get('Labels', {}).get('openqms.owner') != context['test_owner']:
        raise ValueError('test cleanup ownership changed')
    run(['docker', 'rm', '-f', '-v', context['test_container_id']])


def deploy():
    context = validate(os.environ)
    revalidate(context)  # No source material, target secrets or server mutation before eligibility.
    with tempfile.TemporaryDirectory(prefix='openqms-production-') as directory:
        private = Path(directory)
        private.chmod(0o700)
        source = private / 'source'
        source.mkdir()
        sha = context['RELEASE_SHA']
        if run(['git', '-C', str(TRUSTED), 'rev-parse', sha + '^{commit}']).decode().strip() != sha:
            raise ValueError('release commit unavailable')
        archive = run(['git', '-C', str(TRUSTED), 'archive', '--format=tar', sha])
        archive_path = private / 'source.tar'
        archive_path.write_bytes(archive)
        # Git archive entries are verified for regular paths/modes before extraction or transfer.
        with tarfile.open(archive_path) as tar:
            for entry in tar.getmembers():
                parts = Path(entry.name).parts
                if entry.name.startswith('/') or '..' in parts or not (entry.isdir() or entry.isfile()):
                    raise ValueError('unsupported release archive member')
            tar.extractall(source, filter='data')
        paths = run(['git', '-C', str(TRUSTED), 'ls-tree', '-r', '-z', '--name-only', sha])
        manifest = source / '.release-manifest'
        manifest.write_bytes(run([sys.executable, str(TRUSTED / 'scripts/check-release-tree.py'), 'create', '--root', str(source)], data=paths))
        (source / '.release-sha').write_text(sha + '\n')
        context['manifest_hash'] = sha256(manifest)
        context['manifest'] = str(manifest)
        controller = ''.join(f'{sha256(TRUSTED / name)}  {name}\n' for name in sorted(CONTROLLER_FILES))
        context['controller_hash'] = hashlib.sha256(controller.encode()).hexdigest()
        context['source_root'] = str(source)
        # Only trusted default-branch requirements/controllers execute on the
        # credentialed runner. Source archive is data for the isolated builder.
        context['test_root'] = str(TRUSTED)
        run(['python3.11', '-m', 'venv', str(private / 'trusted-venv')])
        context['python'] = str(private / 'trusted-venv/bin/python')
        run([context['python'], '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '-r', str(TRUSTED / 'backend/requirements.txt'), '--index-url', 'https://pypi.org/simple'])
        tunnel = None
        lease = None
        try:
            create_test_database(context, private)  # Must succeed before any target schema mutation.
            revalidate(context)
            payload = private / 'release.tar'
            with tarfile.open(payload, 'w') as tar:
                for path in sorted(source.rglob('*')):
                    if path.is_file():
                        tar.add(path, arcname=path.relative_to(source), recursive=False)
            lease = acquire_lease(context)
            remote(context, 'stage', data=payload.read_bytes())
            remote(context, 'backup')  # Pins previous running image IDs before build retags.
            context['images'] = json.loads(remote(context, 'build'))
            credentials = json.loads(remote(context, 'credentials'))
            with socket.socket() as port_socket:
                port_socket.bind(('127.0.0.1', 0))
                tunnel_port = port_socket.getsockname()[1]
            forward_port = credentials.get('FORWARD_PORT', 5432)
            allowed_ports = {5432} if context['RELEASE_KIND'] == 'production' else {25432, 25433}
            if type(forward_port) is not int or forward_port not in allowed_ports:
                raise ValueError('invalid scoped tunnel endpoint')
            control_socket = private / 'ssh-control'
            # Forward-only connection executes no remote command and cannot bind publicly.
            tunnel = subprocess.Popen(ssh_args(context) + ['-N', '-o', 'ExitOnForwardFailure=yes', '-M', '-S', str(control_socket), '-L', f'127.0.0.1:{tunnel_port}:127.0.0.1:{forward_port}', context['ORACLE_SSH_TARGET']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(30):
                if tunnel.poll() is not None:
                    raise ValueError('target tunnel failed')
                if control_socket.exists():
                    break
                time.sleep(1)
            else:
                raise ValueError('target tunnel not ready')
            context['target_url'] = f"postgresql+asyncpg://{quote(credentials['POSTGRES_USER'], safe='')}:{quote(credentials['POSTGRES_PASSWORD'], safe='')}@127.0.0.1:{tunnel_port}/{quote(credentials['POSTGRES_DB'], safe='')}"
            # Baseline deploy-release owns fixed sequencing. Copy its trusted controller,
            # and provide all phase commands explicitly; candidate deployment scripts never run.
            runner = private / 'runner'
            (runner / 'scripts').mkdir(parents=True)
            (runner / 'backend/.venv/bin').mkdir(parents=True)
            (runner / 'backend/.venv/bin/python').symlink_to(context['python'])
            for name in ('deploy-release.sh', 'check-distinct-databases.py', 'database_identity.py'):
                shutil.copy2(TRUSTED / 'scripts' / name, runner / 'scripts' / name)
            makefile = runner / 'Release.mk'
            makefile.write_text('deploy-release:\n\t@bash scripts/deploy-release.sh\n')
            context_file = private / 'context.json'
            save(context_file, context)
            command = shlex.join([context['python'], str(Path(__file__).resolve()), '--context', str(context_file), '--phase'])
            env = dict(os.environ, TENANT_MODE='single', DATABASE_URL=context['target_url'], TEST_DATABASE_URL=context['test_url'])
            for key, value in {'TARGET_IDENTITY_CMD': 'identity', 'MIGRATE_CMD': 'migrate', 'CHECK_CMD': 'check', 'PREFLIGHT_CMD': 'preflight', 'ROLLOUT_CMD': 'rollout'}.items():
                env[key] = command + ' ' + value
            if context['RELEASE_KIND'] == 'preview':
                env['INITIALIZE_CMD'] = command + ' initialize'
            else:
                env.pop('INITIALIZE_CMD', None)
            env.pop('TENANT_MIGRATE_CMD', None)
            run(['make', '--silent', '-f', str(makefile), '-C', str(runner), 'deploy-release'], env=env)
            print('Oracle release completed')
        finally:
            if tunnel is not None:
                tunnel.terminate()
                try:
                    tunnel.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    tunnel.kill()
                    tunnel.wait()
            if lease is not None:
                lease.stdin.close()
                try:
                    lease.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    lease.terminate()
                    lease.wait(timeout=10)
            cleanup_test(context)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', type=Path)
    parser.add_argument('--phase', choices=('identity', 'migrate', 'check', 'initialize', 'preflight', 'rollout'))
    args = parser.parse_args()
    if args.context is not None and args.phase:
        if args.context.is_symlink() or args.context.stat().st_mode & 0o077:
            raise ValueError('private deployment context required')
        phase(json.loads(args.context.read_text()), args.phase)
    elif args.context is None and args.phase is None:
        deploy()
    else:
        raise ValueError('invalid deployment invocation')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Oracle production release failed; inspect private runner evidence', file=sys.stderr)
        raise SystemExit(1)
