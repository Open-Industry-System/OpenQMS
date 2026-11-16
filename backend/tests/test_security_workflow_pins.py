import re
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('name', ['oracle-deploy.yml', 'oracle-preview-cleanup.yml'])
def test_deployment_actions_are_immutable_and_checkout_repeated_after_transport(name):
    document = yaml.safe_load((ROOT / '.github/workflows' / name).read_text())
    for job in document['jobs'].values():
        for step in job['steps']:
            reference = step.get('uses', '')
            if reference and not reference.startswith('./'):
                assert re.fullmatch(r'[^@]+@[0-9a-f]{40}', reference), reference
    job = document['jobs']['deploy' if 'deploy' in document['jobs'] else 'cleanup']
    steps = job['steps']
    transport = next(i for i, step in enumerate(steps) if step.get('uses', '').startswith('tailscale/'))
    secret = next(i for i, step in enumerate(steps) if 'DEPLOY_KEY' in step.get('env', {}))
    assert any(step.get('uses', '').startswith('actions/checkout@') and step.get('with', {}).get('clean') is True for step in steps[transport + 1:secret])
