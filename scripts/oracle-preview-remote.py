#!/usr/bin/env python3
"""Built-in preview host operations for the shared guarded release pipeline."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess

HERE = Path(__file__).resolve().parent

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

prod = load('preview_prod_contract', 'oracle-production-remote.py')
helper = load('preview_routes', 'oracle-preview.py')
BASE = Path('/var/lib/openqms-previews')

class PreviewRelease:
    def __init__(self, pr, sha, manifest_hash, controller_hash):
        self.pr = helper.pr_number(str(pr))
        if not prod.SHA.fullmatch(sha) or any(not re.fullmatch('[0-9a-f]{64}', value) for value in [manifest_hash, controller_hash]):
            raise ValueError('invalid preview immutable identity')
        self.sha = sha
        self.project = BASE / ('pr-' + self.pr)
        self.root = self.project / 'releases' / sha
        self.source = self.root / 'source'
        self.control = self.root / 'control'
        self.manifest_hash = manifest_hash
        self.controller_hash = controller_hash

    def verify(self):
        for path in (BASE, self.project, self.project / 'releases', self.root, self.source, self.control):
            if path.is_symlink() or not path.is_dir(): raise ValueError('invalid preview directory')
        if prod.digest(self.source / '.release-manifest') != self.manifest_hash or prod.digest(self.control / 'controller.sha256') != self.controller_hash:
            raise ValueError('preview manifest changed')
        expected = set()
        for line in (self.control / 'controller.sha256').read_text().splitlines():
            digest, sep, relative = line.partition('  ')
            if not sep or not re.fullmatch('[0-9a-f]{64}', digest) or not re.fullmatch('[A-Za-z0-9_./-]+', relative) or relative.startswith('/') or '..' in relative.split('/'):
                raise ValueError('invalid trusted manifest')
            if prod.digest(self.control / relative) != digest: raise ValueError('trusted controller changed')
            expected.add(relative)
        if {p.relative_to(self.control).as_posix() for p in self.control.rglob('*') if p.is_file()} != expected | {'controller.sha256'}:
            raise ValueError('trusted controller file set changed')
        prod.run(['python3', str(self.control / 'scripts/check-release-tree.py'), 'verify', '--root', str(self.source), '--manifest', str(self.source / '.release-manifest')])
        if prod.regular(self.source / '.release-sha').read_text() != self.sha + '\n': raise ValueError('release marker changed')

    def settings(self):
        path = prod.regular(self.project / 'preview.env')
        if path.stat().st_mode & 0o077: raise ValueError('unsafe preview secret permissions')
        values = {}
        for line in path.read_text().splitlines():
            key, sep, value = line.partition('=')
            if not sep or key in values: raise ValueError('invalid preview settings')
            values[key] = value
        if set(values) != {'POSTGRES_PASSWORD','REDIS_PASSWORD','NEO4J_PASSWORD','SECRET_KEY','PREVIEW_DB_PORT'}:
            raise ValueError('unexpected preview settings')
        if values['PREVIEW_DB_PORT'] not in {'25432', '25433'} or any(not re.fullmatch('[0-9a-f]{64}', values[key]) for key in values if key != 'PREVIEW_DB_PORT'):
            raise ValueError('invalid preview settings values')
        return values

    def provision(self):
        helper.capacity(self.pr, helper.active_prs())
        path = self.project / 'preview.env'
        if path.exists(): self.settings(); return
        used = set()
        for env in BASE.glob('pr-*/preview.env'):
            for line in prod.regular(env).read_text().splitlines():
                if line.startswith('PREVIEW_DB_PORT='): used.add(line.split('=', 1)[1])
        available = {'25432','25433'} - used
        if not available: raise ValueError('preview database slots exhausted')
        port = sorted(available)[0]
        with socket.socket() as probe: probe.bind(('127.0.0.1', int(port)))
        values = {key: secrets.token_hex(32) for key in ['POSTGRES_PASSWORD','REDIS_PASSWORD','NEO4J_PASSWORD','SECRET_KEY']}
        values['PREVIEW_DB_PORT'] = port
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream: stream.write(''.join(f'{key}={value}\n' for key, value in values.items()))

    def tags(self):
        return {kind: f'openqms-pr-{self.pr}-{kind}:{self.sha}' for kind in ['backend','web']}

    def image_ids(self):
        result = {}
        for kind, tag in self.tags().items():
            item = json.loads(prod.run(['docker','image','inspect',tag]).stdout)[0]
            if not prod.IMAGE.fullmatch(item['Id']) or item['Config'].get('Labels',{}).get('org.opencontainers.image.revision') != self.sha:
                raise ValueError('preview image provenance mismatch')
            result[kind] = item['Id']
        return result

    def assert_images(self, expected):
        if set(expected) != {'backend','web'} or self.image_ids() != expected: raise ValueError('preview image identity changed')

    def compose_command(self, args, images=None):
        self.verify()
        env = {'PATH': os.environ['PATH'], **self.settings(), 'PR_NUMBER':self.pr, 'PREVIEW_INITIALIZER_PATH':str(self.control / 'scripts/oracle-preview-initialize.py')}
        ids = images or self.tags()
        env.update(BACKEND_IMAGE=ids['backend'], WEB_IMAGE=ids['web'])
        return ['docker','compose','--project-name','openqms-pr-'+self.pr,'--project-directory',str(self.source),'--env-file',str(self.project / 'preview.env'),'-f',str(self.control / 'compose.preview.yml'),*args], env

    def compose(self, *args, images=None):
        argv, env = self.compose_command(args, images)
        return prod.run(argv, env=env)

    def backup(self):
        self.verify()
        self.provision()
        # Preview state is disposable; immutable source/manifests are retained.

    def build(self):
        self.verify()
        self.provision()
        if prod.digest(Path('/etc/openqms/preview-Caddyfile')) != prod.digest(self.control / 'deploy/preview-Caddyfile'):
            raise ValueError('preview Caddy installation changed')
        builder = json.loads(prod.run(['docker','inspect','buildx_buildkit_openqms-preview-builder0']).stdout)[0]['HostConfig']
        if not (0 < builder.get('Memory',0) <= 2147483648 and 0 < builder.get('NanoCpus',0) <= 2000000000 and 0 < builder.get('PidsLimit',0) <= 512):
            raise ValueError('bounded preview builder required')
        for kind, dockerfile, context in [('backend','backend/Dockerfile','backend'),('web','frontend/Dockerfile.prod','.')]:
            prod.run(['docker','buildx','build','--builder','openqms-preview-builder','--load','--label','org.opencontainers.image.revision='+self.sha,'--build-arg','RELEASE_SHA='+self.sha,'-t',self.tags()[kind],'-f',str(self.source / dockerfile),str(self.source / context)])
        ids = self.image_ids()
        self.compose('up','-d','--wait','--wait-timeout','240','db','redis','neo4j',images=ids)
        return ids

    def db_container(self):
        rows = helper.resources('container', self.pr)
        matches = [row for row in rows if helper.labels(row,'container').get('com.docker.compose.service') == 'db']
        if len(matches) != 1 or not helper.owned(helper.labels(matches[0],'container'),self.pr) or not matches[0]['State']['Running']:
            raise ValueError('preview database runtime identity failed')
        return matches[0]

    def credentials(self):
        self.verify()
        db = self.db_container()
        values = self.settings()
        if db['NetworkSettings']['Ports'].get('5432/tcp') != [{'HostIp':'127.0.0.1','HostPort':values['PREVIEW_DB_PORT']}]:
            raise ValueError('preview target tunnel endpoint changed')
        return dict(POSTGRES_USER='qms', POSTGRES_DB='qms_preview', POSTGRES_PASSWORD=values['POSTGRES_PASSWORD'], FORWARD_PORT=int(values['PREVIEW_DB_PORT']))

    def identity(self, expected):
        self.verify()
        self.assert_images(expected)
        db = self.db_container()
        return json.loads(prod.run(['docker','exec',db['Id'],'psql','-XAt','-U','qms','-d','qms_preview','-c',prod.SQL]).stdout)

    def app_command(self, expected, *command):
        self.verify()
        self.assert_images(expected)
        nonce = secrets.token_hex(16)
        name = 'openqms-pr-' + self.pr + '-operation-' + nonce
        argv, env = self.compose_command(['run','--rm','--no-deps','--name',name,'--label','openqms.operation.owner='+nonce,'-e','PREVIEW_PR='+self.pr,'backend',*command], expected)
        def interrupted(signum, frame):
            raise RuntimeError('preview operation interrupted')
        handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGHUP, signal.SIGTERM)}
        try:
            result = subprocess.run(argv, env=env, capture_output=True, timeout=900)
            if result.returncode:
                raise RuntimeError('bounded preview application operation failed')
        finally:
            # Finish exact-owner cleanup even when SSH sends another hangup.
            for sig in handlers: signal.signal(sig, signal.SIG_IGN)
            try:
                # Docker client timeout/disconnect must not orphan candidate code.
                found = subprocess.run(['docker','inspect',name], capture_output=True, timeout=30)
                if found.returncode == 0:
                    item = json.loads(found.stdout)[0]
                    labels = item.get('Config',{}).get('Labels',{})
                    if not helper.owned(labels,self.pr) or labels.get('openqms.operation.owner') != nonce or item.get('Image') != expected['backend'] or not re.fullmatch('[0-9a-f]{64}',item.get('Id','')):
                        raise ValueError('preview operation cleanup ownership changed')
                    subprocess.run(['docker','rm','-f',item['Id']], check=True, capture_output=True, timeout=30)
            finally:
                for sig, handler in handlers.items(): signal.signal(sig, handler)

    def migrate(self, expected):
        self.app_command(expected,'python','-m','alembic','upgrade','head')

    def preflight(self, expected):
        self.app_command(expected,'python','-m','app.services.capa_doc_gate_preflight')

    def initialize(self, expected):
        self.app_command(expected,'python','/run/openqms-preview-initialize.py')

    def rollout(self, expected):
        self.verify()
        self.assert_images(expected)
        self.compose('up','-d','--no-build','--wait','--wait-timeout','180','backend','graph-worker','web',images=expected)
        rows = helper.resources('container',self.pr)
        for service, kind in [('backend','backend'),('graph-worker','backend'),('web','web')]:
            matches = [row for row in rows if helper.labels(row,'container').get('com.docker.compose.service') == service]
            if len(matches) != 1 or not helper.owned(helper.labels(matches[0],'container'),self.pr) or not matches[0]['State']['Running'] or matches[0]['Image'] != expected[kind]:
                raise ValueError('preview running image mismatch')
        helper.publish(helper.ROUTES / ('pr-'+self.pr+'.caddy'), helper.route(self.pr), helper.validate, helper.reload)
        helper.atomic(self.project / 'current-release.json', json.dumps({'sha':self.sha,'images':expected,'manifest':self.manifest_hash,'controller':self.controller_hash}))
