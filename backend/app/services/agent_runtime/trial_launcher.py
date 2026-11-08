"""Pinned stdlib worker launcher with private files and bounded owned children."""
import hashlib
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from uuid import UUID

from app.services.agent_runtime.trial_policy import WORKER_PATH, WORKER_SHA256, read_private_file

MAX_OUTPUT = 1024 * 1024


def local_origin(value: str) -> str:
    if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ValueError('invalid origin')
    url = urlsplit(value)
    if (url.scheme not in {'http', 'https'} or url.hostname not in {'127.0.0.1', '::1'}
            or url.username is not None or url.password is not None or url.path not in {'', '/'}
            or '?' in value or '#' in value or (url.port is not None and not 1 <= url.port <= 65535)):
        raise ValueError('invalid origin')
    return value.rstrip('/')


def collect_worker(process: subprocess.Popen, *, timeout: float = 300, limit: int = MAX_OUTPUT):
    """Drain both pipes incrementally; overflow/timeout always reaps this child."""
    buffers = {process.stdout: bytearray(), process.stderr: bytearray()}
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for pipe in buffers:
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('child deadline')
                for key, _ in selector.select(remaining):
                    pipe = key.fileobj
                    chunk = os.read(pipe.fileno(), 8192)
                    if not chunk:
                        selector.unregister(pipe)
                        continue
                    if len(buffers[pipe]) + len(chunk) > limit:
                        raise ValueError('child output limit')
                    buffers[pipe].extend(chunk)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError('child deadline')
            code = process.wait(timeout=remaining)
        return code, bytes(buffers[process.stdout]), bytes(buffers[process.stderr])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise ValueError('child stopped') from None
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for pipe in buffers:
            pipe.close()


def run_fixed_worker(*, installation_id: UUID, secret_file: Path, tenant_slug: str,
                     api_base_url: str, claim_key: str, checkpoint: str, finish: str) -> int:
    try:
        origin = local_origin(api_base_url)
        if (str(UUID(str(installation_id))) != str(installation_id)
                or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', tenant_slug)
                or not isinstance(claim_key, str) or not 1 <= len(claim_key) <= 100
                or checkpoint not in {'off', 'save'} or finish not in {'off', 'completed'}):
            raise ValueError('invalid options')
        secret = read_private_file(Path(secret_file), limit=4096).decode('utf-8').strip()
        if re.fullmatch(r'[A-Za-z0-9_-]{20,72}', secret) is None:
            raise ValueError('invalid credential')
        worker = WORKER_PATH.read_bytes()
        if hashlib.sha256(worker).hexdigest() != WORKER_SHA256:
            raise ValueError('worker mismatch')
        environment = {'LANG': 'C', 'LC_ALL': 'C', 'OPENQMS_API_BASE_URL': origin,
            'OPENQMS_INSTALLATION_ID': str(installation_id), 'OPENQMS_INSTALLATION_SECRET': secret,
            'OPENQMS_TENANT_SLUG': tenant_slug, 'OPENQMS_CLAIM_KEY': claim_key,
            'OPENQMS_READONLY_CHECKPOINT': checkpoint, 'OPENQMS_READONLY_FINISH': finish}
        with tempfile.TemporaryDirectory(prefix='openqms-local-trial-') as directory:
            path = Path(directory) / 'readonly_8d_plugin.py'
            path.write_bytes(worker)
            process = subprocess.Popen([sys.executable, '-I', str(path)], cwd=directory,
                env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            code, output, _ = collect_worker(process)
        if code != 0:
            print('TRIAL_RUN_FAILED', file=sys.stderr)
            return 1
        # Only pinned worker success output; never forward stderr or partial failure output.
        sys.stdout.write(output.decode('utf-8'))
        return 0
    except (OSError, ValueError, TypeError, AttributeError):
        print('TRIAL_LAUNCH_DENIED', file=sys.stderr)
        return 1
