#!/usr/bin/env python3
"""Root-installed receiver for a dedicated forced-command production SSH key."""
import fcntl
import json
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import signal
import select
import re
import shlex
import shutil
import stat
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True

def interrupted(signum, frame):
    raise RuntimeError('deployment SSH channel interrupted')

for _signal in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(_signal, interrupted)

BASE = Path('/var/lib/openqms-releases')
INSTALLED = Path('/usr/local/lib/openqms/oracle-production')
SHARED_ROOT = Path('/usr/local/lib/openqms')
SHARED_MODE = Path('/var/lib/openqms-shared-test')


def command(value):
    parts = shlex.split(value)
    if not parts or parts[0] not in {'production', 'preview'}:
        raise ValueError('unsupported deployment kind')
    kind = parts.pop(0)
    pr = None
    if kind == 'preview':
        if len(parts) < 2 or not re.fullmatch(r'[1-9][0-9]{0,8}', parts[1]):
            raise ValueError('invalid preview identity')
        pr = parts.pop(1)
    if len(parts) not in (4, 5) or parts[0] not in {'lock', 'stage', 'verify', 'backup', 'build', 'identity', 'credentials', 'migrate', 'initialize', 'preflight', 'rollout'}:
        raise ValueError('unsupported deployment command')
    if parts[0] == 'initialize' and kind != 'preview':
        raise ValueError('production initialization forbidden')
    if not re.fullmatch(r'[0-9a-f]{40}', parts[1]) or any(not re.fullmatch(r'[0-9a-f]{64}', item) for item in parts[2:4]):
        raise ValueError('invalid deployment identity')
    if (parts[0] in {'identity', 'migrate', 'initialize', 'preflight', 'rollout'}) != (len(parts) == 5):
        raise ValueError('invalid command arguments')
    return kind, pr, parts


LOCK = Path('/run/lock/openqms-deploy.lock')
LEASE = Path('/run/lock/openqms-deploy-lease.json')
OPERATION = Path('/run/lock/openqms-operation.lock')


def lease_identity(kind, pr, parts):
    return [kind, pr, *parts[1:4]]


class LeaseBusy(BlockingIOError):
    pass


def hold_lock(identity, authorize=None):
    with LOCK.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise LeaseBusy('deployment lease held by another operation') from error
        if authorize is not None:
            authorize()
        LEASE.write_text(json.dumps({'identity': identity, 'pid': os.getpid()}))
        LEASE.chmod(0o600)
        try:
            print('locked', flush=True)
            # Lifetime is the authenticated SSH channel, not a timeout or detached lock.
            while sys.stdin.buffer.read(1):
                pass
        finally:
            LEASE.unlink(missing_ok=True)


def require_lease(identity):
    with LOCK.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lease = json.loads(LEASE.read_text())
            if lease['identity'] != identity:
                raise ValueError('deployment lease identity differs')
            os.kill(lease['pid'], 0)
            return
        raise ValueError('active deployment lease required')


def installed(kind):
    if INSTALLED.is_symlink() or not INSTALLED.is_dir():
        raise ValueError('controller installation missing')
    for path in [INSTALLED, *INSTALLED.rglob('*')]:
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise ValueError('controller must be root-owned and immutable to deployment account')
    filename = 'oracle-production-remote.py' if kind == 'production' else 'oracle-preview-remote.py'
    spec = importlib.util.spec_from_file_location('trusted_oracle_remote', INSTALLED / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stage(parts, factory, base):
    _, sha, manifest_hash, controller_hash = parts
    releases = base / 'releases'
    if BASE.is_symlink() or base.is_symlink() or releases.is_symlink():
        raise ValueError('unsafe release root')
    releases.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.stage-', dir=releases))
    source = temporary / 'source'
    source.mkdir()
    try:
        seen = set()
        total = 0
        with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as archive:
            for entry in archive:
                name = entry.name.rstrip('/')
                path = PurePosixPath(name)
                if path.is_absolute() or any(part in {'', '.', '..'} for part in path.parts) or path.as_posix() != name or name in seen:
                    raise ValueError('invalid archive path')
                seen.add(name)
                target = source.joinpath(*path.parts)
                if entry.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not entry.isfile() or entry.mode not in {0o644, 0o755} or entry.size > 256 * 1024 * 1024:
                    raise ValueError('archive file contract failed')
                total += entry.size
                if total > 1024 * 1024 * 1024:
                    raise ValueError('archive size limit exceeded')
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as output:
                    shutil.copyfileobj(archive.extractfile(entry), output)
                target.chmod(entry.mode)
        shutil.copytree(INSTALLED, temporary / 'control')
        # Verify using exactly the uploaded source and the root-installed control files.
        release = factory(sha, manifest_hash, controller_hash)
        original = release.root
        release.root, release.source, release.control = temporary, source, temporary / 'control'
        release.verify()
        if original.exists():
            existing = factory(sha, manifest_hash, controller_hash)
            existing.verify()
        else:
            temporary.rename(original)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def shared_modules():
    # The queue is installed beside the controller. The queue source never
    # comes from the staged PR, and it is outside the production manifest.
    files = ('oracle-shared-test-remote.py', 'shared-test-queue.py')
    modules = []
    for name in files:
        path = SHARED_ROOT / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('invalid trusted shared-test control file')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules[0], modules[1].Queue


def shared_mode():
    # A malformed or dangling mode path must not re-enable legacy publication.
    return SHARED_MODE.exists() or SHARED_MODE.is_symlink()


def shared_request():
    remote, queue_type = shared_modules()
    if not remote.enabled():
        raise ValueError('shared-test mode unavailable')
    request = remote.read_request(sys.stdin.buffer)
    os.umask(0o077)
    with open(LOCK, 'a') as lock, open(OPERATION, 'a') as operation:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(operation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = remote.run(request, installed('preview'), queue_type)
    print(json.dumps(result), flush=True)


def main():
    # ROLE is fixed by root-owned authorized_keys; the client cannot select it.
    if len(sys.argv) != 3 or sys.argv[1] not in {'production', 'preview'}:
        raise ValueError('forced SSH role required')
    role, original = sys.argv[1:]
    words = shlex.split(original)
    if not words or words[0] != role:
        raise ValueError('cross-role deployment forbidden')
    if words == ['preview', 'queue']:
        shared_request()
        return
    if len(words) == 3 and words[:2] == ['preview', 'cleanup']:
        if not re.fullmatch(r'[1-9][0-9]{0,8}', words[2]):
            raise ValueError('invalid cleanup PR')
        with LOCK.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            operation = OPERATION.open('a')
            fcntl.flock(operation, fcntl.LOCK_EX)
            if shared_mode():
                remote, queue_type = shared_modules()
                remote.guard_legacy_cleanup(queue_type, words[2])
            print('READY', flush=True)
            if not select.select([sys.stdin], [], [], 120)[0] or sys.stdin.readline().strip() != 'CLEANUP':
                raise ValueError('fresh local cleanup confirmation required')
            module = installed('preview')
            module.helper.cleanup(words[2])
        return
    shared = role == 'preview' and shared_mode()
    lease = None
    if role == 'preview' and words[1:2] == ['leased']:
        if not shared or len(words) < 4 or not re.fullmatch('[0-9a-f]{32}', words[2]):
            raise ValueError('invalid shared-test deployment command')
        lease = words[2]
        original = shlex.join([role, *words[3:]])
    elif shared:
        raise ValueError('shared-test deployments require the queue lease')
    kind, pr, parts = command(original)
    identity = lease_identity(kind, pr, parts)
    authorize = None
    if shared:
        remote, queue_type = shared_modules()
        identity.append(lease)

        def authorize():
            remote.require_deploying(queue_type, pr, parts[1], lease)

    if parts[0] == 'lock':
        hold_lock(identity, authorize)
        return
    require_lease(identity)
    with OPERATION.open('a') as operation:
        fcntl.flock(operation, fcntl.LOCK_EX)
        require_lease(identity)
        if authorize is not None:
            authorize()
        dispatch(kind, pr, parts, shared_lease=lease)


def dispatch(kind, pr, parts, *, shared_lease=None):
    module = installed(kind)
    if kind == 'production':
        factory, base = module.Release, BASE
    else:
        factory = lambda sha, manifest, controller: module.PreviewRelease(
            pr, sha, manifest, controller, shared_lease=shared_lease
        )
        base = module.release_base(pr, shared_lease)
    if parts[0] == 'stage':
        stage(parts, factory, base)
        return
    release = factory(parts[1], parts[2], parts[3])
    import json
    action = parts[0]
    if kind == 'preview' and action == 'rollout':
        result = release.rollout(json.loads(parts[4]), publish_route=shared_lease is None)
    else:
        result = getattr(release, action)(json.loads(parts[4])) if len(parts) == 5 else getattr(release, action)()
    if result is not None:
        print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except LeaseBusy:
        print('deployment lease temporarily busy', file=sys.stderr)
        raise SystemExit(75)
    except Exception:
        print('production deployment rejected', file=sys.stderr)
        raise SystemExit(1)
