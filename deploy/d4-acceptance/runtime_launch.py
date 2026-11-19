#!/usr/bin/env python3
"""Start and reclaim the pinned Linux D4 receiver for one acceptance operation.

Only a trusted local executor constructs RuntimeLaunch. The observer receives
a read-only state reader and a deadline. It gathers independent business
evidence while the fixed controller runs. Infrastructure exit codes are never
business evidence.
"""
from contextlib import suppress
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time


ENTRY = 'agent_d4_isolation/deploy/runtime_entry.py'
PACKAGE = 'agent_d4_isolation'
MANIFEST = 'runtime-manifest.json'
RUNTIME_ROOT_ENTRIES = frozenset((
    PACKAGE, MANIFEST, 'deployment.json', 'private', 'state', '.acceptance-launch.lock',
))
HEX64 = re.compile(r'[0-9a-f]{64}')
IMAGE = re.compile(r'sha256:[0-9a-f]{64}')
NONCE_LABEL = 'org.openqms.d4.nonce'
PYTHON = '/usr/bin/python3'
DOCKER = '/usr/bin/docker'
SYSTEMCTL = '/usr/bin/systemctl'


class LaunchError(RuntimeError):
    """The requested runtime operation lacks an exact ownership or cleanup proof."""


def require(condition, code):
    if not condition:
        raise LaunchError(code)


def trusted_directory(path, *, private=False):
    for component in [*reversed(path.parents), path]:
        info = component.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, 'untrusted_runtime_directory')
    if private:
        require(stat.S_IMODE(path.lstat().st_mode) == 0o700, 'runtime_directory_not_private')


def read_owned(path, limit, *, private=False):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                and not info.st_mode & 0o022, 'untrusted_runtime_file')
        if private:
            require(stat.S_IMODE(info.st_mode) == 0o600, 'runtime_file_not_private')
        value = stream.read(limit + 1)
    require(len(value) <= limit, 'runtime_file_too_large')
    return value


def distinct_keys(pairs):
    result = dict(pairs)
    require(len(result) == len(pairs), 'duplicate_runtime_field')
    return result


def decode(raw):
    value = json.loads(raw, object_pairs_hook=distinct_keys)
    require(type(value) is dict, 'invalid_runtime_record')
    return value


def verify_bundle(root, pin):
    trusted_directory(root, private=True)
    # The fixed entry installs this root on sys.path. A sibling module such
    # as subprocess.py could shadow a library even if package hashes match.
    require(all(path.name in RUNTIME_ROOT_ENTRIES for path in root.iterdir()),
            'runtime_root_contains_unreviewed_entry')
    raw = read_owned(root / MANIFEST, 65536, private=True)
    require(hashlib.sha256(raw).hexdigest() == pin, 'runtime_manifest_mismatch')
    declared = decode(raw)
    require(ENTRY in declared, 'runtime_entry_missing')
    found = set()
    pending = [root / PACKAGE]
    while pending:
        directory = pending.pop()
        trusted_directory(directory)
        for path in directory.iterdir():
            relative = path.relative_to(root).as_posix()
            if stat.S_ISDIR(path.lstat().st_mode):
                pending.append(path)
            else:
                found.add(relative)
                expected = declared.get(relative)
                require(isinstance(expected, str) and HEX64.fullmatch(expected), 'runtime_file_unlisted')
                content = read_owned(path, 2 * 1024 * 1024)
                require(hashlib.sha256(content).hexdigest() == expected, 'runtime_file_mismatch')
    require(found == set(declared), 'runtime_bundle_file_set_mismatch')


def run_command(arguments, *, cwd, timeout):
    result = subprocess.run(
        arguments, cwd=cwd, env={}, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False,
    )
    require(result.returncode == 0 and len(result.stdout) <= 65536, 'runtime_command_failed')
    return result.stdout


class RuntimeLaunch:
    def __init__(self, root, manifest_sha256, nonce, api_container_id, *, timeout=40):
        path = PurePosixPath(str(root))
        require(path.is_absolute() and '..' not in path.parts and path != PurePosixPath('/'),
                'invalid_runtime_root')
        for value in (manifest_sha256, nonce, api_container_id):
            require(isinstance(value, str) and HEX64.fullmatch(value), 'invalid_runtime_identity')
        require(type(timeout) is int and 1 <= timeout <= 40, 'invalid_runtime_timeout')
        self.root = Path(path)
        self.manifest_sha256 = manifest_sha256
        self.nonce = nonce
        self.api_container_id = api_container_id
        self.timeout = timeout

    def command(self, role):
        require(role in ('launch', 'maintain'), 'unsupported_runtime_role')
        return [PYTHON, '-I', '-S', '-B', str(self.root / ENTRY), role, '--nonce', self.nonce]

    def record(self, relative):
        path = self.root / relative
        try:
            trusted_directory(path.parent, private=True)
            record = decode(read_owned(path, 16384, private=True))
        except FileNotFoundError:
            return None
        require(record.get('nonce') == self.nonce, 'runtime_record_nonce_mismatch')
        return record

    def read_state(self):
        state = self.record('state/' + self.nonce + '.json')
        if state is None:
            return None
        require(state.get('schema_version') == 1 and state.get('phase') in ('prepare', 'delivery', 'reclaim'),
                'invalid_runtime_state')
        preparation = state.get('preparation')
        require(type(preparation) is dict, 'invalid_runtime_preparation')
        if preparation:
            require(preparation.get('api_container_id') == self.api_container_id,
                    'runtime_api_identity_changed')
        return state

    def journal(self):
        return self.record('state/journal/' + self.nonce + '.json')

    def deployment(self):
        record = decode(read_owned(self.root / 'deployment.json', 16384, private=True))
        require(record.get('schema_version') == 1 and record.get('api_container_id') == self.api_container_id,
                'runtime_deployment_identity_mismatch')
        permit = record.get('permit')
        require(type(permit) is dict and permit.get('api_uid') == 2002 and permit.get('receiver_uid') == 2001,
                'runtime_uid_permit_mismatch')
        image = permit.get('image_digest')
        require(isinstance(image, str) and IMAGE.fullmatch(image), 'runtime_image_unpinned')
        return image

    def wait_reclaimed(self, deadline):
        while time.monotonic() < deadline:
            journal = self.journal()
            if journal and journal.get('state') == 'closed':
                require(journal.get('closed_by') == 'reclaim_verified'
                        and journal.get('doubted') is False, 'receiver_reclaim_unverified')
                return journal
            time.sleep(0.05)
        raise LaunchError('receiver_reclaim_timeout')

    def remove_receiver(self, journal, image):
        receiver = journal.get('container_id')
        require(isinstance(receiver, str) and HEX64.fullmatch(receiver), 'invalid_receiver_identity')
        state = self.read_state()
        require(state and state.get('create_converged') is True and state.get('receiver_id') == receiver,
                'receiver_state_identity_mismatch')
        snapshot = state.get('snapshot') or {}
        require(snapshot.get('container_id') == receiver and snapshot.get('image_id') == image
                and snapshot.get('api_container_id') == self.api_container_id
                and snapshot.get('nonce') == self.nonce, 'receiver_snapshot_mismatch')
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        daemon = run_command(
            [SYSTEMCTL, 'show', 'docker.service', '--property=InvocationID', '--value'],
            cwd='/', timeout=3,
        ).decode().strip()
        require(boot and daemon and boot == snapshot.get('boot_id')
                and daemon == snapshot.get('daemon_invocation'), 'receiver_host_identity_changed')

        def listed():
            return run_command(
                [DOCKER, 'container', 'ls', '-a', '-q', '--no-trunc',
                 '--filter', f'label={NONCE_LABEL}={self.nonce}'],
                cwd='/', timeout=5,
            ).decode().splitlines()

        matches = listed()
        if not matches:
            return
        require(matches == [receiver], 'receiver_inventory_mismatch')
        raw = run_command([DOCKER, 'container', 'inspect', receiver], cwd='/', timeout=5)
        rows = json.loads(raw)
        require(type(rows) is list and len(rows) == 1, 'invalid_receiver_inventory')
        row = rows[0]
        require(row.get('Id') == receiver and row.get('Image') == image
                and row.get('Config', {}).get('Labels', {}).get(NONCE_LABEL) == self.nonce
                and row.get('HostConfig', {}).get('NetworkMode') == 'container:' + self.api_container_id
                and row.get('State', {}).get('Running') is False, 'receiver_ownership_unverified')
        run_command([DOCKER, 'container', 'rm', receiver], cwd='/', timeout=5)
        require(not listed(), 'receiver_removal_unverified')

    def maintain(self):
        # The native service retains ambiguous journal state and never grants
        # launch authority to a nonce whose creation did not converge.
        try:
            subprocess.run(
                self.command('maintain'), cwd='/', env={}, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def run(self, observe):
        require(sys.platform == 'linux' and os.geteuid() == 0, 'trusted_linux_executor_required')
        verify_bundle(self.root, self.manifest_sha256)
        image = self.deployment()
        descriptor = os.open(self.root / '.acceptance-launch.lock',
                             os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'rb') as lock:
            info = os.fstat(lock.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                    and stat.S_IMODE(info.st_mode) == 0o600, 'invalid_runtime_launch_lock')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LaunchError('runtime_launch_busy') from None
            require(self.journal() is None and self.read_state() is None, 'runtime_nonce_has_been_used')
            deadline = time.monotonic() + self.timeout
            process = subprocess.Popen(
                self.command('launch'), cwd='/', env={}, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                evidence = observe(self.read_state, deadline)
                require(evidence is not None, 'runtime_business_evidence_missing')
                require(time.monotonic() < deadline, 'runtime_operation_expired')
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
                require(code == 1, 'unexpected_runtime_launch_status')
                journal = self.wait_reclaimed(deadline)
                state = self.read_state()
                require(state and state.get('watchdog_bound_verified') is True
                        and type(state.get('first_stdin_ns')) is int, 'runtime_delivery_unverified')
                self.remove_receiver(journal, image)
                return evidence
            except BaseException:
                with suppress(OSError, subprocess.TimeoutExpired):
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=3)
                self.maintain()
                # Cleanup may now be definitive. It must not convert the
                # failed operation into an acceptance result.
                try:
                    journal = self.journal()
                    if (journal and journal.get('state') == 'closed'
                            and journal.get('closed_by') == 'reclaim_verified'):
                        self.remove_receiver(journal, image)
                except (OSError, ValueError, LaunchError, subprocess.TimeoutExpired):
                    pass
                raise
