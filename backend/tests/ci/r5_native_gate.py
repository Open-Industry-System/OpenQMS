"""Native CI entry; runner hook supplies one fresh job-owned PostgreSQL bundle.

This entry never provisions, searches for, or deletes Docker resources. A missing
runner/hook is an unavailable required check, never a passing or skipped gate.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

from tests.ci.owned_resources import verify_owned_instance, verify_owned_database


def bundle_environment(path: Path, source, *, platform=sys.platform, now=None):
    if platform!='darwin':
        raise ValueError('R5 native CI requires Darwin sandbox-exec')
    mode=path.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError('R5 bundle must be an owner-only regular file')
    bundle=json.loads(path.read_text())
    for name in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_JOB'):
        if not source.get(name) or bundle.get(name)!=source[name]:
            raise ValueError('R5 bundle does not belong to this CI job')
    age=(time.time() if now is None else now)-bundle['created_unix']
    if not 0<=age<=900:
        raise ValueError('R5 bundle is not freshly provisioned')
    registration=Path(bundle['OPENQMS_TEST_RESOURCE_FILE'])
    resource=json.loads(registration.read_text())
    if not bundle.get('owner_nonce') or resource.get('owner_nonce')!=bundle['owner_nonce']:
        raise ValueError('R5 bundle owner does not match registration')
    env={key:value for key,value in source.items() if key in ('PATH','HOME','TMPDIR','LANG','LC_ALL')}
    env.update(TEST_DATABASE_URL=bundle['TEST_DATABASE_URL'],
        OPENQMS_TEST_RESOURCE_FILE=str(registration),PG15_CONTAINER=resource['container_id'],
        SECRET_KEY='r5-native-ci-ephemeral-test-only',PYTHONDONTWRITEBYTECODE='1',
        OPENQMS_CI_SHA=source.get('GITHUB_SHA',''),
        OPENQMS_TEST_ARTIFACTS=source.get('OPENQMS_TEST_ARTIFACTS',str(path.parent/'r5-safe')))
    target=verify_owned_instance(env)
    verify_owned_database(target)
    return env


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:raise ValueError('explicit runner hook bundle required')
    env=bundle_environment(Path(args[0]),os.environ)
    root=Path(__file__).resolve().parents[3]
    # Preinstalled Python/dependencies, Node and Chromium are runner obligations;
    # no fallback credentials, package installation or browser download here.
    return subprocess.run(['make','check-r5-native','PYTHON_BIN='+sys.executable],cwd=root,env=env).returncode


if __name__=='__main__':raise SystemExit(main())
