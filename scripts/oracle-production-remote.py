#!/usr/bin/env python3
"""Trusted production host operations; candidate source supplies no deployment commands."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile

BASE = Path('/var/lib/openqms-releases')
APP = Path('/opt/openqms')
SHA = re.compile(r'[0-9a-f]{40}')
IMAGE = re.compile(r'sha256:[0-9a-f]{64}')
SQL = "SELECT json_build_object('system_identifier',(pg_control_system()).system_identifier::text,'database',current_database(),'database_oid',(SELECT oid::bigint FROM pg_database WHERE datname=current_database()))"


def run(argv, *, env=None, data=None, okay=False):
    result = subprocess.run(argv, input=data, capture_output=True, env=env)
    if result.returncode and not okay:
        raise RuntimeError('production host command failed')
    return result


def regular(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('required regular file unavailable')
    return path


def digest(path):
    return hashlib.sha256(regular(path).read_bytes()).hexdigest()


def settings():
    """Do not source dotenv or permit Compose interpolation/ambient overrides."""
    path = regular(APP / '.env.production')
    if path.stat().st_mode & 0o077:
        raise ValueError('production environment permissions must be 0600')
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in values or '$' in value or '\x00' in value:
            raise ValueError('invalid production environment')
        values[key] = value
    required = set("SITE_ADDRESS TAILSCALE_IP POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL REDIS_PASSWORD REDIS_URL NEO4J_USER NEO4J_PASSWORD NEO4J_URI NEO4J_DATABASE SECRET_KEY ACCESS_TOKEN_EXPIRE_MINUTES REFRESH_TOKEN_EXPIRE_DAYS ALGORITHM GRAPH_REPOSITORY TENANT_MODE E2E_MODE LLM_PROVIDER LLM_API_KEY LLM_MODEL LLM_BASE_URL EMBEDDING_PROVIDER EMBEDDING_API_KEY EMBEDDING_MODEL EMBEDDING_BASE_URL VITE_PUBLIC_DEMO_ENABLED VITE_PUBLIC_DEMO_USERNAME VITE_PUBLIC_DEMO_PASSWORD".split())
    empty = {key for key in required if key.startswith(('LLM_', 'EMBEDDING_'))}
    if values.keys() - required - {'VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS'} or any(not values.get(key) for key in required - empty):
        raise ValueError('unknown or empty production setting')
    if values.get('ALGORITHM') != 'HS256' or not all(re.fullmatch(r'[0-9a-f]{48}', values.get(key, '')) for key in ('REDIS_PASSWORD', 'NEO4J_PASSWORD')):
        raise ValueError('production configuration contract failed')
    if values.get('REDIS_URL') != 'redis://:' + values.get('REDIS_PASSWORD', '') + '@redis:6379/0':
        raise ValueError('production internal Redis contract failed')
    if not required <= values.keys() or values['TENANT_MODE'] != 'single' or values['E2E_MODE'] != 'false':
        raise ValueError('production settings contract failed')
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', values['POSTGRES_USER']) or not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', values['POSTGRES_DB']):
        raise ValueError('invalid database identifier')
    if not re.fullmatch(r'[0-9a-f]{48}', values['POSTGRES_PASSWORD']) or not re.fullmatch(r'[0-9a-f]{96}', values['SECRET_KEY']):
        raise ValueError('production secret contract failed')
    expected = f"postgresql+asyncpg://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}@db:5432/{values['POSTGRES_DB']}"
    if values['DATABASE_URL'] != expected:
        raise ValueError('production internal database contract failed')
    return values


class Release:
    def __init__(self, sha, manifest_hash, controller_hash):
        if not SHA.fullmatch(sha) or not re.fullmatch(r'[0-9a-f]{64}', manifest_hash) or not re.fullmatch(r'[0-9a-f]{64}', controller_hash):
            raise ValueError('invalid release identity')
        self.sha = sha
        self.root = BASE / 'releases' / sha
        self.source = self.root / 'source'
        self.control = self.root / 'control'
        self.manifest_hash = manifest_hash
        self.controller_hash = controller_hash

    def verify(self):
        for path in (BASE, BASE / 'releases', self.root, self.source, self.control):
            if path.is_symlink() or not path.is_dir():
                raise ValueError('release directory contract failed')
        if digest(self.source / '.release-manifest') != self.manifest_hash:
            raise ValueError('release manifest changed')
        # The controller checksum pins its complete trusted file set including this helper.
        manifest = regular(self.control / 'controller.sha256')
        if digest(manifest) != self.controller_hash:
            raise ValueError('controller manifest changed')
        lines = manifest.read_text().splitlines()
        expected = set()
        for line in lines:
            checksum, sep, relative = line.partition('  ')
            if not sep or not re.fullmatch(r'[0-9a-f]{64}', checksum) or not re.fullmatch(r'[A-Za-z0-9_./-]+', relative) or relative.startswith('/') or '..' in relative.split('/'):
                raise ValueError('invalid controller manifest')
            expected.add(relative)
            if digest(self.control / relative) != checksum:
                raise ValueError('controller file changed')
        if {p.relative_to(self.control).as_posix() for p in self.control.rglob('*') if p.is_file()} != expected | {'controller.sha256'}:
            raise ValueError('controller file set changed')
        run(['python3', str(self.control / 'scripts/check-release-tree.py'), 'verify', '--root', str(self.source), '--manifest', str(self.source / '.release-manifest')])
        if regular(self.source / '.release-sha').read_text() != self.sha + '\n':
            raise ValueError('release marker changed')
        settings()

    def compose(self, *args, okay=False, extra=None):
        self.verify()
        env = {key: os.environ[key] for key in ('PATH', 'HOME', 'DOCKER_HOST', 'DOCKER_CONTEXT') if key in os.environ}
        env['RELEASE_SHA'] = self.sha
        command = ['docker', 'compose', '--project-name', 'openqms', '--project-directory', str(self.source), '--env-file', str(APP / '.env.production'), '-f', str(self.control / 'docker-compose.prod.yml'), '-f', str(self.control / 'deploy/preview-edge.override.yml')]
        if extra:
            command += ['-f', str(extra)]
        return run(command + list(args), env=env, okay=okay)

    def image_ids(self):
        ids = {}
        for service, tag in (('backend', 'openqms-backend:prod'), ('web', 'openqms-web:prod')):
            entry = json.loads(run(['docker', 'image', 'inspect', tag]).stdout)[0]
            image_id = entry['Id']
            if not IMAGE.fullmatch(image_id) or entry['Config'].get('Labels', {}).get('org.opencontainers.image.revision') != self.sha:
                raise ValueError('image provenance failed')
            ids[service] = image_id
        return ids

    def assert_images(self, expected):
        if set(expected) != {'backend', 'web'} or self.image_ids() != expected:
            raise ValueError('image identity changed')

    def runtime(self):
        rows = []
        for service in ('db', 'backend', 'graph-worker', 'web'):
            payload = json.loads(run(['docker', 'inspect', f'openqms-{service}-1']).stdout)[0]
            labels = payload['Config'].get('Labels', {})
            if labels.get('com.docker.compose.project') != 'openqms' or labels.get('com.docker.compose.service') != service or not payload['State']['Running']:
                raise ValueError('active runtime identity failed')
            if not IMAGE.fullmatch(payload['Image']):
                raise ValueError('active runtime image failed')
            rows.append((service, payload['Image']))
        return dict(rows)

    def backup(self):
        self.verify()
        # Record running image IDs before build retags anything. Never mutate the active source.
        old = self.runtime()
        state = {'previous_images': old}
        (self.root / 'previous-runtime.json').write_text(json.dumps(state))
        backup_dir = APP / 'backups/postgres'
        backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if backup_dir.is_symlink():
            raise ValueError('invalid backup directory')
        fd, partial = tempfile.mkstemp(prefix='.release-', suffix='.partial', dir=backup_dir)
        published = backup_dir / f'oracle-{self.sha}-{Path(partial).name.removeprefix(".release-").removesuffix(".partial")}.dump'
        try:
            values = settings()
            with os.fdopen(fd, 'wb') as stream:
                dumped = subprocess.run(['docker', 'exec', 'openqms-db-1', 'pg_dump', '-Fc', '-U', values['POSTGRES_USER'], '-d', values['POSTGRES_DB']], stdout=stream, stderr=subprocess.PIPE)
                if dumped.returncode:
                    raise ValueError('database backup failed')
            if not Path(partial).stat().st_size:
                raise ValueError('backup is empty')
            with Path(partial).open('rb') as stream:
                listed = subprocess.run(['docker', 'exec', '-i', 'openqms-db-1', 'pg_restore', '--list'], stdin=stream, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if listed.returncode:
                raise ValueError('database backup validation failed')
            # Non-overwriting publication; a redeploy keeps the existing earlier backup.
            try:
                os.link(partial, published, follow_symlinks=False)
            except FileExistsError:
                if not published.is_file() or published.is_symlink() or not published.stat().st_size:
                    raise ValueError('existing backup invalid')
        finally:
            Path(partial).unlink(missing_ok=True)

    def build(self):
        self.verify()
        # Edge configuration is a one-time trusted host installation, never PR content.
        if digest(Path('/etc/openqms/production-edge-Caddyfile')) != digest(self.control / 'deploy/production-edge-Caddyfile'):
            raise ValueError('installed production edge configuration changed')
        routes = Path('/etc/openqms/preview-routes')
        if routes.is_symlink() or not routes.is_dir():
            raise ValueError('preview route directory unavailable')
        run(['docker', 'network', 'inspect', 'openqms-preview-edge'])
        self.compose('config', '--quiet')
        self.compose('build')
        return self.image_ids()

    def identity(self, expected):
        self.verify()
        self.assert_images(expected)
        self.runtime()
        values = settings()
        result = run(['docker', 'exec', 'openqms-db-1', 'psql', '-XAt', '-U', values['POSTGRES_USER'], '-d', values['POSTGRES_DB'], '-c', SQL])
        return json.loads(result.stdout)

    def credentials(self):
        self.verify()
        values = settings()
        return {key: values[key] for key in ('POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD')}

    def app_command(self, expected, *command):
        self.verify()
        self.assert_images(expected)
        # No source/controller/key mounts. Only this application's own dotenv
        # reaches the bounded target container; the host never imports candidate code.
        nonce = secrets.token_hex(16)
        name = 'openqms-operation-' + nonce
        argv = ['docker', 'run', '--rm', '--name', name, '--label', 'openqms.operation.owner=' + nonce, '--cpus', '2', '--memory', '2g', '--pids-limit', '256', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--network', 'openqms_openqms_internal', '--env-file', str(APP / '.env.production'), expected['backend'], *command]
        try:
            result = subprocess.run(argv, capture_output=True, timeout=900)
            if result.returncode:
                raise RuntimeError('bounded production application operation failed')
        finally:
            # A timed-out/interrupted Docker client must not leave candidate code running.
            found = subprocess.run(['docker', 'inspect', name], capture_output=True)
            if found.returncode == 0:
                item = json.loads(found.stdout)[0]
                if item['Config'].get('Labels', {}).get('openqms.operation.owner') != nonce or not re.fullmatch(r'[0-9a-f]{64}', item['Id']):
                    raise ValueError('application operation cleanup ownership changed')
                run(['docker', 'rm', '-f', item['Id']])


    def migrate(self, expected):
        self.app_command(expected, 'python', '-m', 'alembic', 'upgrade', 'head')

    def preflight(self, expected):
        self.app_command(expected, 'python', '-m', 'app.services.capa_doc_gate_preflight')

    def rollout(self, expected):
        self.verify()
        self.assert_images(expected)
        old = json.loads(regular(self.root / 'previous-runtime.json').read_text())['previous_images']
        if set(old) != {'db', 'backend', 'graph-worker', 'web'} or not all(IMAGE.fullmatch(value) for value in old.values()):
            raise ValueError('rollback runtime unavailable')
        try:
            self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180', 'backend', 'graph-worker', 'web')
            # Verify actual live containers, not only mutable tags.
            actual = self.runtime()
            if actual['backend'] != expected['backend'] or actual['graph-worker'] != expected['backend'] or actual['web'] != expected['web']:
                raise ValueError('running release images differ')
        except Exception:
            # Restore pinned running image IDs; source and DB never automatically roll back.
            rollback = self.root / 'rollback-images.json'
            rollback.write_text(json.dumps({'services': {name: {'image': old[name]} for name in ('backend', 'graph-worker', 'web')}}))
            self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180', 'backend', 'graph-worker', 'web', extra=rollback)
            raise RuntimeError('rollout failed; prior application images restored')
        (self.root / 'release-metadata.json').write_text(json.dumps({'sha': self.sha, 'manifest_hash': self.manifest_hash, 'controller_hash': self.controller_hash, 'images': expected}))
        temporary = BASE / '.current-release-next'
        if temporary.exists() or temporary.is_symlink():
            raise ValueError('current release transition already exists')
        temporary.symlink_to(self.root)
        os.replace(temporary, BASE / 'current-release')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('verify', 'backup', 'build', 'identity', 'credentials', 'rollout'))
    parser.add_argument('--sha', required=True)
    parser.add_argument('--manifest-hash', required=True)
    parser.add_argument('--controller-hash', required=True)
    parser.add_argument('--images')
    args = parser.parse_args()
    release = Release(args.sha, args.manifest_hash, args.controller_hash)
    if args.action in {'identity', 'rollout'}:
        result = getattr(release, args.action)(json.loads(args.images or '{}'))
    else:
        result = getattr(release, args.action)()
    if result is not None:
        print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('oracle production operation failed', file=sys.stderr)
        raise SystemExit(1)
