from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ.pop('ALLOW_SEED_DB_TESTS', None)
os.environ['SECRET_KEY'] = 'test-secret-key-for-ci-pure-only'
os.environ['TEST_DATABASE_URL'] = (
    'postgresql+asyncpg://ci_pure:ci_pure@127.0.0.1:1/openqms_ci_pure_test'
)


os.environ['OPENQMS_CI_PURE'] = '1'
os.chdir(ROOT / 'backend')
sys.path.insert(0, str(ROOT / 'backend'))
from tests.ci.python_isolation import bootstrap

bootstrap()
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
