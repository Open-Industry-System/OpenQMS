import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHA = 'a' * 40
NEW = {'backend': 'sha256:' + 'b' * 64, 'web': 'sha256:' + 'c' * 64}
OLD = {'db': 'sha256:' + '1' * 64, 'backend': 'sha256:' + '2' * 64, 'graph-worker': 'sha256:' + '2' * 64, 'web': 'sha256:' + '3' * 64}


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def local_config(tmp_path):
    key = tmp_path / 'key'
    key.write_text('private fake key')
    key.chmod(0o600)
    known = tmp_path / 'known'
    known.write_text('host ssh-ed25519 fake')
    return dict(RELEASE_SHA=SHA, RELEASE_KIND='production', ORACLE_SSH_TARGET='openqms-deploy@oracle.example', ORACLE_SSH_KEY=str(key), ORACLE_KNOWN_HOSTS=str(known), ORACLE_REVALIDATE_CMD='exit 0')


@pytest.mark.parametrize('field,value', [('RELEASE_SHA', '../unsafe'), ('RELEASE_KIND', 'unknown'), ('ORACLE_SSH_TARGET', 'ubuntu@oracle.example'), ('ORACLE_SSH_TARGET', 'openqms-deploy@host;id'), ('DATABASE_URL', 'production-secret'), ('TEST_DATABASE_URL', 'shared-test'), ('ORACLE_REVALIDATE_CMD', '')])
def test_invalid_config_fails_before_external_command(local_config, field, value):
    local_config[field] = value
    with pytest.raises(ValueError):
        module('deploy-oracle-release').validate(local_config)


def test_failed_revalidation_never_executes_source_or_ssh(tmp_path, local_config):
    calls = tmp_path / 'calls'
    local_config['ORACLE_REVALIDATE_CMD'] = f'printf denied > {calls}; exit 1'
    env = dict(os.environ, **local_config)
    env.pop('DATABASE_URL', None)
    env.pop('TEST_DATABASE_URL', None)
    result = subprocess.run([str(ROOT / 'scripts/deploy-oracle-release.sh')], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert calls.read_text() == 'denied'
    assert 'private fake key' not in result.stdout + result.stderr


@pytest.mark.parametrize('raw', ['id', 'stage ../x x y', f'rollout {SHA} ' + 'b'*64 + ' ' + 'c'*64, f'verify {SHA} ' + 'b'*64 + ' ' + 'c'*64 + ' extra', f'build {SHA} ' + 'b'*64 + ' ' + 'c'*64 + '; id'])
def test_forced_receiver_rejects_extra_commands_before_controller_load(raw):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/oracle-deploy-receiver.py'), raw], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stderr.strip() == 'production deployment rejected'


@pytest.fixture
def host(tmp_path, monkeypatch):
    helper = module('oracle-production-remote')
    base = tmp_path / 'openqms'
    root = base / 'releases' / SHA
    source, control = root / 'source', root / 'control'
    source.mkdir(parents=True)
    (control / 'scripts').mkdir(parents=True)
    (control / 'deploy').mkdir()
    (source / 'README.md').write_text('immutable code\n')
    (source / '.release-sha').write_text(SHA + '\n')
    manifest = f"100644 {hashlib.sha256((source / 'README.md').read_bytes()).hexdigest()}  README.md\n"
    (source / '.release-manifest').write_text(manifest)
    (source / 'README.md').chmod(0o644)
    shutil.copyfile(ROOT / 'scripts/check-release-tree.py', control / 'scripts/check-release-tree.py')
    for path in ('docker-compose.prod.yml', 'deploy/preview-edge.override.yml', 'deploy/production-edge-Caddyfile'):
        (control / path).write_text('trusted runtime template\n')
    controller = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(control)}\n' for p in sorted(control.rglob('*')) if p.is_file())
    (control / 'controller.sha256').write_text(controller)
    values = dict(POSTGRES_USER='qms', POSTGRES_DB='qms', POSTGRES_PASSWORD='f'*48, SECRET_KEY='e'*96, TENANT_MODE='single', E2E_MODE='false')
    for key in "SITE_ADDRESS TAILSCALE_IP NEO4J_USER NEO4J_URI NEO4J_DATABASE ACCESS_TOKEN_EXPIRE_MINUTES REFRESH_TOKEN_EXPIRE_DAYS GRAPH_REPOSITORY VITE_PUBLIC_DEMO_ENABLED VITE_PUBLIC_DEMO_USERNAME VITE_PUBLIC_DEMO_PASSWORD".split():
        values[key] = 'configured'
    values['ALGORITHM'] = 'HS256'
    values['REDIS_PASSWORD'] = values['NEO4J_PASSWORD'] = 'd' * 48
    values['REDIS_URL'] = 'redis://:' + values['REDIS_PASSWORD'] + '@redis:6379/0'
    for key in "LLM_PROVIDER LLM_API_KEY LLM_MODEL LLM_BASE_URL EMBEDDING_PROVIDER EMBEDDING_API_KEY EMBEDDING_MODEL EMBEDDING_BASE_URL".split():
        values[key] = ''
    values['DATABASE_URL'] = f"postgresql+asyncpg://qms:{'f'*48}@db:5432/qms"
    (base / '.env.production').write_text(''.join(f'{k}={v}\n' for k,v in values.items()))
    (base / '.env.production').chmod(0o600)
    monkeypatch.setattr(helper, 'BASE', base)
    monkeypatch.setattr(helper, 'APP', base)
    fake = tmp_path / 'bin'
    fake.mkdir()
    log = tmp_path / 'docker-calls.jsonl'
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({'runtime': OLD, 'fail_up': False}))
    program = '''#!/usr/bin/env python3
import sys,json,os
from pathlib import Path
args=sys.argv[1:]
log=Path(LOG)
with log.open('a') as f:f.write(json.dumps({'args':args,'env':{k:v for k,v in os.environ.items() if k.startswith('COMPOSE') or k=='DATABASE_URL'}})+'\\n')
p=Path(STATE);state=json.loads(p.read_text())
if args[:2]==['image','inspect']:
 service='backend' if args[2].startswith('openqms-backend') else 'web'
 print(json.dumps([{'Id':NEW[service],'Config':{'Labels':{'org.opencontainers.image.revision':SHA}}}]))
elif args[0]=='inspect':
 if args[1].startswith('openqms-operation-'):sys.exit(1)
 service=args[1].removeprefix('openqms-').removesuffix('-1')
 print(json.dumps([{'Image':state['runtime'][service],'Config':{'Labels':{'com.docker.compose.project':'openqms','com.docker.compose.service':service}},'State':{'Running':True}}]))
elif args[0]=='compose':
 if 'up' in args:
  if state['fail_up']:
   state['fail_up']=False;p.write_text(json.dumps(state));sys.exit(1)
  if any(a.endswith('rollback-images.json') for a in args):
   state['runtime']=OLD
  else:state['runtime']={**OLD,'backend':NEW['backend'],'graph-worker':NEW['backend'],'web':NEW['web']}
  p.write_text(json.dumps(state))
elif args[0]=='run':pass
else:sys.exit(2)
'''
    program = program.replace('LOG', repr(str(log))).replace('STATE', repr(str(state)))
    program = program.replace("args=sys.argv[1:]", f"args=sys.argv[1:]\nNEW={NEW!r}\nOLD={OLD!r}\nSHA={SHA!r}")
    docker = fake / 'docker'
    docker.write_text(program)
    docker.chmod(0o755)
    monkeypatch.setenv('PATH', str(fake) + os.pathsep + os.environ['PATH'])
    release = helper.Release(SHA, hashlib.sha256(manifest.encode()).hexdigest(), hashlib.sha256(controller.encode()).hexdigest())
    return helper, release, source, control, log, state


def test_remote_tamper_blocks_every_compose_action(host):
    helper, release, source, control, log, state = host
    (source / 'README.md').write_text('changed source')
    with pytest.raises(RuntimeError):
        release.compose('up', '-d', 'backend')
    assert not log.exists()


def test_remote_controller_tamper_blocks_execution(host):
    _, release, source, control, log, state = host
    (control / 'docker-compose.prod.yml').write_text('changed commands')
    with pytest.raises(ValueError, match='controller file changed'):
        release.compose('build')
    assert not log.exists()


def test_remote_image_retag_blocks_rollout(host):
    _, release, source, control, log, state = host
    with pytest.raises(ValueError, match='identity changed'):
        release.rollout({'backend': OLD['backend'], 'web': OLD['web']})
    calls = [json.loads(line)['args'] for line in log.read_text().splitlines()]
    assert all(args[0] != 'compose' for args in calls)


def test_failed_rollout_restores_pinned_prior_images_without_publishing_pointer(host, monkeypatch):
    _, release, source, control, log, state = host
    (release.root / 'previous-runtime.json').write_text(json.dumps({'previous_images': OLD}))
    state.write_text(json.dumps({'runtime': OLD, 'fail_up': True}))
    monkeypatch.setenv('COMPOSE_FILE', '/hostile.yml')
    monkeypatch.setenv('DATABASE_URL', 'secret-ambient')
    with pytest.raises(RuntimeError, match='prior application images restored'):
        release.rollout(NEW)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    compose = [call for call in calls if call['args'][0] == 'compose']
    assert len(compose) == 2
    assert compose[0]['env'] == compose[1]['env'] == {}
    rollback = json.loads((release.root / 'rollback-images.json').read_text())
    assert rollback['services']['backend']['image'] == OLD['backend']
    assert rollback['services']['web']['image'] == OLD['web']
    assert not (release.root.parents[1] / 'current-release').exists()
    assert json.loads(state.read_text())['runtime'] == OLD


def test_success_checks_live_images_before_atomic_current_pointer(host):
    _, release, source, control, log, state = host
    (release.root / 'previous-runtime.json').write_text(json.dumps({'previous_images': OLD}))
    release.rollout(NEW)
    assert (release.root.parents[1] / 'current-release').resolve() == release.root
    args = [json.loads(line)['args'] for line in log.read_text().splitlines()]
    assert any('preview-edge.override.yml' in part for call in args for part in call)

@pytest.mark.parametrize('mutation', ['unknown_key', 'missing_redis', 'placeholder_algorithm', 'wrong_redis_secret'])
def test_production_env_contract_rejects_unsafe_compose_inputs(host, mutation):
    _, release, source, control, log, state = host
    envfile = release.root.parents[1] / '.env.production'
    text = envfile.read_text()
    if mutation == 'unknown_key': text += 'COMPOSE_FILE=/hostile.yml\n'
    elif mutation == 'missing_redis': text = '\n'.join(line for line in text.splitlines() if not line.startswith('REDIS_PASSWORD=')) + '\n'
    elif mutation == 'placeholder_algorithm': text = text.replace('ALGORITHM=HS256', 'ALGORITHM=none')
    else: text = text.replace('REDIS_URL=redis://:', 'REDIS_URL=redis://:wrong')
    envfile.write_text(text)
    with pytest.raises(ValueError):
        release.compose('up', '-d', 'backend')
    assert not log.exists()


def test_receiver_protocol_scopes_preview_initialization_and_ids():
    receiver = module('oracle-deploy-receiver')
    hashes = ' ' + 'b' * 64 + ' ' + 'c' * 64
    assert receiver.command(f'preview initialize 17 {SHA}{hashes} {{}}') == ('preview', '17', ['initialize', SHA, 'b' * 64, 'c' * 64, '{}'])
    with pytest.raises(ValueError):
        receiver.command(f'production initialize {SHA}{hashes} {{}}')
    with pytest.raises(ValueError):
        receiver.command(f'preview build 017 {SHA}{hashes}')


def test_persistent_host_lease_matches_identity_and_dies_with_channel(tmp_path):
    receiver = module('oracle-deploy-receiver')
    receiver.LOCK, receiver.LEASE = tmp_path / 'lock', tmp_path / 'lease'
    identity = ['preview', '17', SHA, 'b' * 64, 'c' * 64]
    script = tmp_path / 'holder.py'
    script.write_text(f'''import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('receiver',{str(ROOT / 'scripts/oracle-deploy-receiver.py')!r})
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.LOCK=Path({str(receiver.LOCK)!r});m.LEASE=Path({str(receiver.LEASE)!r})
m.hold_lock({identity!r})
''')
    process = subprocess.Popen([sys.executable, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        assert process.stdout.readline() == b'locked\n'
        receiver.require_lease(identity)
        with pytest.raises(ValueError, match='identity differs'):
            receiver.require_lease(['production', None, SHA, 'b' * 64, 'c' * 64])
        with pytest.raises(BlockingIOError):
            receiver.hold_lock(identity)
    finally:
        process.stdin.close()
        assert process.wait(timeout=5) == 0
    assert not receiver.LEASE.exists()
    with pytest.raises(ValueError, match='active deployment lease required'):
        receiver.require_lease(identity)


def test_shared_preview_config_requires_pr_and_pins_known_hosts(local_config):
    local = module('deploy-oracle-release')
    local_config['RELEASE_KIND'] = 'preview'
    with pytest.raises(ValueError):
        local.validate(local_config)
    local_config['PREVIEW_PR'] = '17'
    context = local.validate(local_config)
    assert context['PREVIEW_PR'] == '17'
    args = local.ssh_args(context)
    assert 'StrictHostKeyChecking=yes' in args
    assert 'UserKnownHostsFile=' + context['ORACLE_KNOWN_HOSTS'] in args
    assert '-tt' not in args


def test_checks_env_removes_target_and_provider_secrets_and_ambient_ci_identity(local_config, monkeypatch):
    local = module('deploy-oracle-release')
    monkeypatch.setenv('DATABASE_URL', 'production-secret')
    monkeypatch.setenv('ORACLE_SSH_KEY', '/production/key')
    monkeypatch.setenv('LLM_API_KEY', 'provider-secret')
    monkeypatch.setenv('GITHUB_RUN_ID', 'ambient')
    monkeypatch.setenv('PGSERVICE', 'ambient-db-service')
    context = {'test_url': 'postgresql+asyncpg://test:temp@127.0.0.1:15400/qms_test', 'resource': '/private/resource', 'python': '/private/venv/python'}
    env = local.test_environment(context)
    assert env['DATABASE_URL'] == env['TEST_DATABASE_URL'] == context['test_url']
    assert not {'LLM_API_KEY', 'ORACLE_SSH_KEY', 'GITHUB_RUN_ID', 'PGSERVICE'} & env.keys()


@pytest.mark.parametrize('role,command', [('preview', f'production credentials {SHA} '+ 'b'*64 +' '+ 'c'*64), ('production', 'preview cleanup 17'), ('production', f'preview lock 17 {SHA} '+ 'b'*64 +' '+ 'c'*64)])
def test_forced_receiver_role_cannot_cross_environments(role, command):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/oracle-deploy-receiver.py'), role, command], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stderr.strip() == 'production deployment rejected'


def test_check_phase_attests_unprivileged_ci_without_running_candidate_code(monkeypatch):
    local = module('deploy-oracle-release')
    calls = []
    monkeypatch.setattr(local, 'revalidate', lambda context: calls.append('exact CI receipt'))
    monkeypatch.setattr(local, 'tracked_unchanged', lambda context: calls.append('immutable source'))
    monkeypatch.setattr(local, 'run', lambda *args, **kwargs: pytest.fail('candidate executable on credentialed runner'))
    local.phase({}, 'check')
    assert calls == ['exact CI receipt', 'immutable source']


def test_migration_and_preflight_only_dispatch_bounded_target_operations(monkeypatch):
    import types
    local = module('deploy-oracle-release')
    identity = object()
    fake = types.ModuleType('database_identity')
    fake.DatabaseIdentity = types.SimpleNamespace(from_json=lambda payload: identity)
    fake.resolve_live_identity = lambda dsn: identity
    monkeypatch.setitem(sys.modules, 'database_identity', fake)
    calls = []
    monkeypatch.setattr(local, 'remote', lambda context, action: calls.append(action) or b'{}')
    monkeypatch.setattr(local, 'run', lambda *args, **kwargs: pytest.fail('candidate executable on credentialed runner'))
    local.phase({'target_url': 'not-a-real-connection'}, 'migrate')
    local.phase({'target_url': 'not-a-real-connection'}, 'preflight')
    assert calls == ['verify', 'identity', 'migrate', 'verify', 'identity', 'preflight']


def test_production_migration_and_preflight_only_run_in_bounded_own_env_container(host):
    _, release, source, control, log, state = host
    release.migrate(NEW)
    release.preflight(NEW)
    commands = [json.loads(line)['args'] for line in log.read_text().splitlines()]
    operations = [args for args in commands if args[0] == 'run']
    assert len(operations) == 2
    for args in operations:
        assert args[args.index('--cpus') + 1] == '2'
        assert args[args.index('--memory') + 1] == '2g'
        assert args[args.index('--pids-limit') + 1] == '256'
        assert args[args.index('--env-file') + 1] == str(release.root.parents[1] / '.env.production')
        assert args[args.index('--network') + 1] == 'openqms_openqms_internal'
        assert NEW['backend'] in args
        assert not {'-v', '--volume', '--mount', '--privileged', '--network=host'} & set(args)
    assert operations[0][-5:] == ['python', '-m', 'alembic', 'upgrade', 'head']
    assert operations[1][-3:] == ['python', '-m', 'app.services.capa_doc_gate_preflight']


def test_cleanup_waits_for_orphaned_inflight_operation_before_ready_or_deleting(tmp_path):
    import fcntl
    import select
    operation = tmp_path / 'operation'
    deleted = tmp_path / 'deleted'
    script = tmp_path / 'cleanup.py'
    script.write_text(f'''import importlib.util,sys,types
from pathlib import Path
spec=importlib.util.spec_from_file_location('receiver',{str(ROOT / 'scripts/oracle-deploy-receiver.py')!r})
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.LOCK=Path({str(tmp_path / 'global')!r});m.OPERATION=Path({str(operation)!r})
m.installed=lambda kind:types.SimpleNamespace(helper=types.SimpleNamespace(cleanup=lambda pr:Path({str(deleted)!r}).write_text(pr)))
sys.argv=['receiver','preview','preview cleanup 17']
m.main()
''')
    with operation.open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        process = subprocess.Popen([sys.executable, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            # Global lease is absent, but an earlier in-flight operation still owns
            # the secondary lock. Cleanup cannot even announce READY yet.
            assert not select.select([process.stdout], [], [], 0.3)[0]
            assert not deleted.exists()
            fcntl.flock(held, fcntl.LOCK_UN)
            assert select.select([process.stdout], [], [], 5)[0]
            assert process.stdout.readline() == b'READY\n'
            assert not deleted.exists()
            process.stdin.write(b'CLEANUP\n')
            process.stdin.flush()
            process.stdin.close()
            assert process.wait(timeout=5) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
    assert deleted.read_text() == '17'
