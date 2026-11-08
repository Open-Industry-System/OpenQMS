"""Exercise real Make release recipes with a harmless Python environment probe."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('target', ['doc-gate-preflight', 'deploy-migrate'])
@pytest.mark.parametrize(('secret', 'legacy', 'expected'), [
    ('operator-secret', None, 'operator-secret'),
    (None, None, None),
    (None, 'explicit-legacy-secret', 'explicit-legacy-secret'),
    ('operator-secret', 'explicit-legacy-secret', 'operator-secret'),
])
def test_release_recipe_preserves_configured_secret(tmp_path, target, secret, legacy, expected):
    probe = tmp_path / 'probe.py'
    result = tmp_path / 'environment.json'
    probe.write_text(
        'import json, os\n'
        'from pathlib import Path\n'
        'Path(os.environ["PROBE_OUTPUT"]).write_text(json.dumps(os.environ.get("SECRET_KEY")))\n'
    )
    environment = {key: value for key, value in os.environ.items()
                   if key not in {'SECRET_KEY', 'PYTEST_SECRET_KEY', 'MAKEFLAGS', 'MFLAGS', 'MAKELEVEL'}}
    environment.update(DATABASE_URL='postgresql://unused.invalid/never_connected', PROBE_OUTPUT=str(result))
    if secret is not None:
        environment['SECRET_KEY'] = secret
    if legacy is not None:
        environment['PYTEST_SECRET_KEY'] = legacy
    completed = subprocess.run(
        ['make', '--no-print-directory', '-f', str(ROOT / 'Makefile'), target,
         f'BACKEND_DIR={tmp_path}', f'PYTHON_BIN={sys.executable} {probe}'],
        cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(result.read_text()) == expected
