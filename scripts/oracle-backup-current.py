#!/usr/bin/env python3
"""Root-installed timer entry using the validated active immutable production release."""
import fcntl
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def main():
    with Path('/run/lock/openqms-deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        installed = Path('/usr/local/lib/openqms/oracle-production/scripts/oracle-production-remote.py')
        if installed.is_symlink() or installed.stat().st_uid != 0 or installed.stat().st_mode & 0o022:
            raise ValueError('trusted backup controller unavailable')
        spec = importlib.util.spec_from_file_location('oracle_backup', installed)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        current = module.BASE / 'current-release'
        if not current.is_symlink():
            raise ValueError('active release pointer unavailable')
        root = current.resolve(strict=True)
        root.relative_to(module.BASE / 'releases')
        data = json.loads((root / 'release-metadata.json').read_text())
        release = module.Release(data['sha'], data['manifest_hash'], data['controller_hash'])
        if release.root != root:
            raise ValueError('active release pointer differs')
        release.backup()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('active production backup failed', file=sys.stderr)
        raise SystemExit(1)
