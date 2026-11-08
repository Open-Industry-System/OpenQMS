from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ.pop('ALLOW_SEED_DB_TESTS', None)
os.environ['SECRET_KEY'] = 'test-secret-key-for-ci-pure-only'
os.environ['TEST_DATABASE_URL'] = (
    'postgresql+asyncpg://ci_pure:ci_pure@127.0.0.1:1/openqms_ci_pure_test'
)


def reject_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
        raise RuntimeError('pure_test_network_forbidden')


sys.addaudithook(reject_network)
os.chdir(ROOT / 'backend')
sys.path.insert(0, str(ROOT / 'backend'))
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
