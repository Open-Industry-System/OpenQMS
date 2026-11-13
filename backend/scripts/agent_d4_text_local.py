"""Run the fixed receiver in a private stdlib-only POSIX child session.

Only the config filename and expected public worker SHA256 appear in argv.
The caller supplies the trusted deployment hash; this tool does not grant access.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from uuid import UUID

WORKER = Path(__file__).resolve().parents[1] / 'examples/readonly_d4_text_receiver.py'
SESSION_SECONDS = 60
GRACE_SECONDS = .2
CONFIG_LIMIT = 64 * 1024


class LaunchFailure(Exception):
    def __init__(self):
        super().__init__('configuration_invalid')


def require(condition):
    if not condition:
        raise LaunchFailure()


def unique_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def _read_private_config(path):
    """Open relative to a verified, pinned owner-only directory; no symlinks."""
    path = Path(os.path.abspath(path))
    directory = path.parent
    # Reject symlinks in every provided path component, including directory.
    for component in (*reversed(directory.parents), directory):
        require(not stat.S_ISLNK(component.lstat().st_mode))
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory_fd)
        require(stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.getuid())
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600)
            require(info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size <= CONFIG_LIMIT)
            raw = handle.read(CONFIG_LIMIT+1)
            require(len(raw) <= CONFIG_LIMIT)
    finally:
        os.close(directory_fd)
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_pairs)
    require(type(value) is dict and set(value) == {'origin', 'tenant_slug', 'installation_id', 'secret', 'request_key', 'expected_report_id'})
    require(all(type(item) is str for item in value.values()))
    origin = value['origin']
    require(not any(ord(c) <= 32 or ord(c) >= 127 for c in origin) and not any(c in origin for c in ('?', '#', '\\')))
    parsed = urlsplit(origin)
    require(parsed.scheme in ('http', 'https') and parsed.hostname in ('127.0.0.1', '::1'))
    require(parsed.username is None and parsed.password is None and parsed.path == '')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    require(1 <= port <= 65535)
    authority = '[::1]' if parsed.hostname == '::1' else '127.0.0.1'
    require(parsed.netloc in (authority, authority+':'+str(port)))
    require(re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', value['tenant_slug']) is not None)
    for key in ('installation_id', 'expected_report_id'):
        require(str(UUID(value[key])) == value[key])
    require(20 <= len(value['secret']) <= 200 and 1 <= len(value['request_key']) <= 100)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def read_private_config(path):
    result = None
    try:
        result = _read_private_config(path)
    except Exception:
        pass
    if result is None:
        raise LaunchFailure()
    return result


def cleanup_group(process):
    """Always clean this start_new_session child's group, including early exit."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    # The leader may already have exited while a descendant still owns its group.
    time.sleep(GRACE_SECONDS)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def supervise(source, config):
    process = None
    with tempfile.TemporaryDirectory(prefix='openqms-d4-') as private:
        private = os.path.realpath(private)
        os.chmod(private, 0o700)
        worker = Path(private) / 'receiver.py'
        fd = os.open(worker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(source)
        # Only a verified immutable snapshot executes. No user site, SDK, .env,
        # shell, provider credentials, proxy settings or repository cwd.
        environment = {'HOME': private, 'TMPDIR': private}
        deadline = time.monotonic() + SESSION_SECONDS
        try:
            process = subprocess.Popen([sys.executable, '-I', '-S', '-B', str(worker)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=private, env=environment, start_new_session=True, close_fds=True)
            output, _ = process.communicate(config, timeout=max(.001, deadline-time.monotonic()))
            require(time.monotonic() < deadline and len(output) <= 1024)
            result = json.loads(output.decode('utf-8'), object_pairs_hook=unique_pairs)
            require(type(result) is dict)
            status = result.get('status')
            require(status in ('completed', 'unconfirmed', 'input_unconfirmed', 'unknown', 'rejected', 'configuration_invalid'))
            require(type(result.get('received_fields')) is int and result['received_fields'] in (0, 1))
            if status == 'completed':
                require(process.returncode == 0 and set(result) == {'status', 'received_fields', 'receipt_id'})
                require(type(result['receipt_id']) is str and str(UUID(result['receipt_id'])) == result['receipt_id'])
                return dict(status=status, received_fields=result['received_fields'], receipt_id=result['receipt_id'])
            require(set(result) == {'status', 'received_fields'} and result['received_fields'] == 0)
            return dict(status=status, received_fields=0)
        finally:
            if process is not None:
                cleanup_group(process)
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()


def launch(config_path, expected_sha256):
    try:
        require(os.name == 'posix')
        require(type(expected_sha256) is str and re.fullmatch(r'[a-f0-9]{64}', expected_sha256) is not None)
        config = read_private_config(config_path)
        fd = os.open(WORKER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as handle:
            require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode))
            source = handle.read(1024*1024+1)
        require(len(source) <= 1024*1024 and hashlib.sha256(source).hexdigest() == expected_sha256)
    except Exception:
        return {'status': 'configuration_invalid', 'received_fields': 0}
    try:
        return supervise(source, config)
    except Exception:
        # A killed session could have sent finish. Never infer a remote state.
        return {'status': 'unknown', 'received_fields': 0}


def main():
    parser = argparse.ArgumentParser(description='Fixed local D4 receiver launcher')
    parser.add_argument('--config', required=True)
    parser.add_argument('--worker-sha256', required=True)
    args = parser.parse_args()
    result = launch(args.config, args.worker_sha256)
    print(json.dumps(result, separators=(',', ':')))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    sys.exit(main())
