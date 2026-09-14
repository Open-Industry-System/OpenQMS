#!/usr/bin/env python3
"""Verify a tunneled database is the database running on the Oracle host."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys

from database_identity import (
    DatabaseIdentity,
    DatabaseIdentityError,
    resolve_live_identity,
)


_SSH_CONNECT_TIMEOUT_SECONDS = 10
_SSH_PROCESS_TIMEOUT_SECONDS = 60

_REMOTE_SQL = (
    "SELECT json_build_object('system_identifier', "
    "(pg_control_system()).system_identifier::text, 'database', "
    "current_database(), 'database_oid', (SELECT oid::bigint FROM pg_database "
    "WHERE datname = current_database()))"
)


def _remote_identity_command(app_dir: str) -> str:
    psql_command = (
        'psql -XAt -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
        f'-c "{_REMOTE_SQL}"'
    )
    return (
        f"cd {shlex.quote(app_dir)} && unset DATABASE_URL TEST_DATABASE_URL && "
        "./scripts/production-compose.sh "
        f"exec -T db sh -ec {shlex.quote(psql_command)}"
    )


def verify_runtime_target_identity(
    *, dsn: str, ssh_target: str, ssh_key: str, app_dir: str
) -> None:
    """Compare the local tunneled identity with the remote Compose database."""
    local_identity = resolve_live_identity(dsn)
    ssh_argv = [
        "ssh",
        "-i",
        ssh_key,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        f"ConnectTimeout={_SSH_CONNECT_TIMEOUT_SECONDS}",
        ssh_target,
        _remote_identity_command(app_dir),
    ]
    try:
        result = subprocess.run(
            ssh_argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=_SSH_PROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise DatabaseIdentityError("ssh command timed out") from None
    if result.returncode != 0:
        raise DatabaseIdentityError("ssh command failed")

    lines = result.stdout.splitlines()
    if len(lines) != 1 or not lines[0].strip():
        raise DatabaseIdentityError("invalid remote identity")
    try:
        remote_identity = DatabaseIdentity.from_json(lines[0])
    except DatabaseIdentityError:
        raise DatabaseIdentityError("invalid remote identity") from None
    if remote_identity != local_identity:
        raise DatabaseIdentityError("identity mismatch")


def main() -> int:
    required = (
        "DATABASE_URL",
        "ORACLE_SSH_TARGET",
        "ORACLE_SSH_KEY",
        "ORACLE_APP_DIR",
    )
    if any(not os.environ.get(name) for name in required):
        print(
            "runtime target identity guard failed: missing configuration",
            file=sys.stderr,
        )
        return 2

    try:
        verify_runtime_target_identity(
            dsn=os.environ["DATABASE_URL"],
            ssh_target=os.environ["ORACLE_SSH_TARGET"],
            ssh_key=os.environ["ORACLE_SSH_KEY"],
            app_dir=os.environ["ORACLE_APP_DIR"],
        )
    except DatabaseIdentityError as exc:
        print(f"runtime target identity guard failed: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print(
            "runtime target identity guard failed: local identity unavailable",
            file=sys.stderr,
        )
        return 2

    print("runtime target identity guard OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
