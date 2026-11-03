"""Prepare one verified disposable PostgreSQL database for CI acceptance tests."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Mapping

from tests.ci.owned_resources import (
    VerifiedTestTarget,
    ensure_test_database,
    verify_owned_database,
    verify_owned_instance,
)


_RETIRED_CONNECTION_KEYS = ('PGHOST', 'PGPORT', 'PGUSER', 'PGPASSWORD', 'TEST_DB', 'PGADMIN_URL')


def run_migrations(target: VerifiedTestTarget, database_url: str) -> None:
    """Run public Alembic migrations only against the verified target URL."""
    environment = dict(os.environ)
    for key in _RETIRED_CONNECTION_KEYS:
        environment.pop(key, None)
    environment['DATABASE_URL'] = database_url
    environment['TEST_DATABASE_URL'] = database_url
    subprocess.run(
        [sys.executable, '-c',
         'from tests.ci.python_isolation import bootstrap; bootstrap(); '
         'import runpy; runpy.run_module("alembic", run_name="__main__")',
         'upgrade', 'head'],
        cwd=Path(__file__).resolve().parents[2], env=environment, check=True,
    )


def prepare_database(source: Mapping[str, str]) -> str:
    """Verify instance, create only its target, verify it, then migrate it."""
    target = verify_owned_instance(source)
    ensure_test_database(target)
    database_url = verify_owned_database(target)
    run_migrations(target, database_url)
    return database_url


def main() -> int:
    prepare_database(os.environ)
    print('verified test database prepared')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
